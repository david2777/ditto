from __future__ import annotations
import random
import requests
from typing import *
from pathlib import Path
from datetime import datetime

from loguru import logger
from sqlalchemy import String, ForeignKey, Integer, DateTime, create_engine, select, update, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, Session, sessionmaker

from ditto import constants, image_processing
from ditto.constants import QueryDirection
from ditto.utilities.timer import Timer

OUTPUT_DIR = Path(constants.OUTPUT_DIR).resolve()


# 1. Setup Base and Models
class Base(DeclarativeBase):
    pass


class Quote(Base):
    __tablename__ = "quotes"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    db_id: Mapped[str] = mapped_column(String)
    content: Mapped[str] = mapped_column(String)
    title: Mapped[Optional[str]] = mapped_column(String)
    author: Mapped[Optional[str]] = mapped_column(String)
    image_url: Mapped[Optional[str]] = mapped_column(String)
    image_expiry: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    @property
    def image_path_raw(self) -> Path:
        """Returns the path for the "raw" unprocessed image on disk weather or not it exits."""
        return OUTPUT_DIR / 'raw' / f'{self.id}.jpg'

    def get_image_path_processed(self, width: int, height: int) -> Path:
        """Returns the path for the processed image on disk weather or not it exits."""
        return OUTPUT_DIR / 'processed' / f'{self.id}-{width}x{height}.jpg'

    def download_image(self) -> bool:
        """Attempt to download the image from the image URL and store it as the raw image."""
        if not self.image_url:
            return False

        t = Timer()
        logger.debug(f'Downloading image at {self.image_url}...')
        try:
            with requests.Session() as session:
                response = session.get(self.image_url)
                if response.status_code == 200:
                    self.image_path_raw.parent.mkdir(parents=True, exist_ok=True)
                    with open(self.image_path_raw.as_posix(), "wb") as f:
                        f.write(response.content)
            logger.debug(f'Took {t.get_elapsed_time()} to download image')
            return True
        except Exception as e:
            logger.error(f"Error downloading image: {e}")
            return False

    def process_image(self, width: Optional[int] = None, height: Optional[int] = None) -> Optional[Path]:
        """Processed the image and saved out the processed image. If an image does not exist, use a fallback image."""
        width = width or constants.DEFAULT_WIDTH
        height = height or constants.DEFAULT_HEIGHT
        fallback_image_path = Path.cwd() / Path('resources/fallback.png')

        output_path = self.get_image_path_processed(width, height)
        image_path_raw = self.image_path_raw

        if output_path.is_file() and constants.CACHE_ENABLED:
            return output_path

        if constants.USE_STATIC_BG:
            image_path_raw = fallback_image_path
        elif not image_path_raw.is_file():
            if self.image_url:
                self.download_image()
            else:
                image_path_raw = fallback_image_path

        # If download failed and we have no file, use fallback
        if not image_path_raw.is_file():
             image_path_raw = fallback_image_path

        t = Timer()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            result = image_processing.process_image(image_path_raw.as_posix(), output_path.as_posix(),
                                                    (width, height), self.content, self.title or "", self.author or "")
            if result:
                logger.debug(f'Took {t.get_elapsed_time()} to process image: {output_path.as_posix()}')
                return output_path
            else:
                logger.error(f'Failed to process image: {output_path.as_posix()}')
                return None
        except Exception as e:
            logger.exception(f"Error processing image: {e}")
            return None


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    client_name: Mapped[str] = mapped_column(String, unique=True)
    current_position: Mapped[int] = mapped_column(Integer, default=-1)

    # Relationship to their specific shuffled deck
    sequence: Mapped[List["ClientSequence"]] = relationship(back_populates="client")


class ClientSequence(Base):
    __tablename__ = "client_sequences"

    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), primary_key=True)
    quote_id: Mapped[str] = mapped_column(ForeignKey("quotes.id"), primary_key=True)
    position: Mapped[int] = mapped_column(Integer, primary_key=True)

    client: Mapped["Client"] = relationship(back_populates="sequence")
    quote: Mapped["Quote"] = relationship()


# 2. The Engine Manager
class QuoteManager:
    def __init__(self, db_url: str = "sqlite:///quotes.db"):
        self.engine = create_engine(db_url)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def upsert_quote(self, quote_data: dict):
        """Insert or update a quote."""
        with self.Session() as session:
            stmt = select(Quote).where(Quote.id == quote_data['id'])
            existing = session.scalar(stmt)
            
            if existing:
                # Update existing fields
                for key, value in quote_data.items():
                    if hasattr(existing, key):
                        setattr(existing, key, value)
            else:
                # Create new
                new_quote = Quote(**quote_data)
                session.add(new_quote)
            
            session.commit()

    def register_client(self, client_name: str):
        with self.Session() as session:
            # Check if client exists
            client = session.scalar(select(Client).where(Client.client_name == client_name))
            if client:
                # Ensure they have a sequence if they exist but somehow no sequence? 
                # (Logic handled in sync_new_quotes, but effectively we assume if client exists, they might need sync)
                return client

            # Create new client
            new_client = Client(client_name=client_name)
            session.add(new_client)
            session.flush()  # Get the ID before committing

            # Create the shuffled deck
            all_quote_ids = session.scalars(select(Quote.id)).all()
            shuffled_ids = list(all_quote_ids)
            random.shuffle(shuffled_ids)

            sequences = [
                ClientSequence(client_id=new_client.id, quote_id=qid, position=idx)
                for idx, qid in enumerate(shuffled_ids)
            ]
            session.add_all(sequences)
            session.commit()
            return new_client

    def sync_new_quotes(self, client_name: str):
        """Ensure the client has all available quotes in their sequence."""
        with self.Session() as session:
            # 1. Get the client
            client = session.scalar(select(Client).where(Client.client_name == client_name))
            if not client:
                # Need to register first? Or just return
                return

            # 2. Find Quote IDs the client DOES NOT have in their sequence yet
            existing_quote_ids_stmt = (
                select(ClientSequence.quote_id)
                .where(ClientSequence.client_id == client.id)
            )

            new_quotes_stmt = (
                select(Quote.id)
                .where(Quote.id.not_in(existing_quote_ids_stmt))
            )
            new_quote_ids = list(session.scalars(new_quotes_stmt).all())

            if not new_quote_ids:
                return  # Everything is already synced

            # 3. Shuffle only the new quotes
            random.shuffle(new_quote_ids)

            # 4. Find the current max position for this client
            max_pos = session.scalar(
                select(func.max(ClientSequence.position))
                .where(ClientSequence.client_id == client.id)
            )
            # If max_pos is None (empty deck), start at -1 so first item is at 0
            if max_pos is None:
                max_pos = -1

            # 5. Append them
            new_sequences = [
                ClientSequence(client_id=client.id, quote_id=qid, position=max_pos + 1 + idx)
                for idx, qid in enumerate(new_quote_ids)
            ]

            session.add_all(new_sequences)
            session.commit()
            logger.info(f"Synced {len(new_quote_ids)} new quotes for {client_name}.")

    def _get_quote_at_position(self, session: Session, client: Client, position: int) -> Optional[Quote]:
        stmt = (
            select(Quote)
            .join(ClientSequence)
            .where(ClientSequence.client_id == client.id)
            .where(ClientSequence.position == position)
        )
        return session.scalar(stmt)

    def get_quote(self, client_name: str, direction: QueryDirection) -> Optional[Quote]:
        """High-level method to get a quote based on direction."""
        
        # Ensure client exists and is synced
        self.register_client(client_name)
        self.sync_new_quotes(client_name)
        
        with self.Session() as session:
            client = session.scalar(select(Client).where(Client.client_name == client_name))
            if not client:
                return None # Should not happen due to register_client call above

            # Get total count of quotes for this client
            count_stmt = select(func.count(ClientSequence.quote_id)).where(ClientSequence.client_id == client.id)
            total_count = session.scalar(count_stmt) or 0
            
            if total_count == 0:
                return None

            current_pos = client.current_position
            new_pos = current_pos

            if direction == QueryDirection.CURRENT:
                # If -1 (just started), move to 0
                if current_pos < 0:
                    new_pos = 0
            elif direction == QueryDirection.FORWARD:
                new_pos = current_pos + 1
                if new_pos >= total_count:
                    new_pos = 0 # Loop back to start
            elif direction == QueryDirection.REVERSE:
                new_pos = current_pos - 1
                if new_pos < 0:
                    new_pos = total_count - 1 # Loop back to end
            elif direction == QueryDirection.RANDOM:
                new_pos = random.randint(0, total_count - 1)
            
            # Update client position
            # Note: We need to use `update` or set attribute and commit
            # Re-fetch client to ensure it's attached to this session or assume it is
            client.current_position = new_pos
            session.add(client)
            session.commit()
            
            return self._get_quote_at_position(session, client, new_pos)
