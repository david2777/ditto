from __future__ import annotations
import random
import requests
from typing import List, Optional
from pathlib import Path
from datetime import datetime

from loguru import logger
from sqlalchemy import String, ForeignKey, Integer, DateTime, create_engine, select, func, inspect, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, Session, sessionmaker

from ditto import image_processing
from ditto.config import settings
from ditto.constants import QueryDirection
from ditto.utilities.timer import Timer

OUTPUT_DIR = Path(settings.output_dir).resolve()


# 1. Setup Base and Models
class Base(DeclarativeBase):
    pass


class Quote(Base):
    """SQLAlchemy model representing a quote sourced from Notion.

    Attributes:
        id: Unique identifier for the quote (from Notion).
        db_id: Identifier of the Notion database this quote belongs to.
        content: The quote text.
        title: Optional title or source name for the quote.
        author: Optional author of the quote.
        image_url: Optional URL pointing to a background image hosted on Notion.
        image_expiry: Optional expiry timestamp for the Notion-hosted ``image_url``.
    """

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
        """Return the path for the raw, unprocessed image on disk whether or not it exists.

        Returns:
            The resolved file path for the raw image.
        """
        return OUTPUT_DIR / "raw" / f"{self.id}.jpg"

    def get_image_path_processed(self, width: int, height: int) -> Path:
        """Return the path for the processed image on disk whether or not it exists.

        Args:
            width: Target image width in pixels.
            height: Target image height in pixels.

        Returns:
            The resolved file path for the processed image, including dimensions in the filename.
        """
        return OUTPUT_DIR / "processed" / f"{self.id}-{width}x{height}.jpg"

    def download_image(self) -> bool:
        """Download the image from ``image_url`` and save it as the raw image file.

        If ``image_url`` is not set the download is skipped.

        Returns:
            ``True`` if the image was downloaded successfully, ``False`` otherwise.
        """
        if not self.image_url:
            return False

        t = Timer()
        logger.debug(f"Downloading image at {self.image_url}...")
        try:
            with requests.Session() as session:
                response = session.get(self.image_url)
                if response.status_code == 200:
                    self.image_path_raw.parent.mkdir(parents=True, exist_ok=True)
                    with open(self.image_path_raw.as_posix(), "wb") as f:
                        f.write(response.content)
            logger.debug(f"Took {t.get_elapsed_time()} to download image")
            return True
        except Exception as e:
            logger.error(f"Error downloading image: {e}")
            return False

    def process_image(self, width: Optional[int] = None, height: Optional[int] = None) -> Optional[Path]:
        """Process the quote's background image and save the result to disk.

        If a raw image does not exist locally it will be downloaded first.  When no image is
        available at all, a bundled fallback image is used instead.  Results are cached on disk
        when ``settings.cache_enabled`` is ``True``.

        Args:
            width: Target width in pixels.  Defaults to ``settings.default_width``.
            height: Target height in pixels.  Defaults to ``settings.default_height``.

        Returns:
            The path to the processed image file, or ``None`` if processing failed.
        """
        width = width or settings.default_width
        height = height or settings.default_height
        fallback_image_path = Path.cwd() / Path("resources/fallback.png")

        output_path = self.get_image_path_processed(width, height)
        image_path_raw = self.image_path_raw

        if output_path.is_file() and settings.cache_enabled:
            return output_path

        if settings.use_static_bg:
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
            result = image_processing.process_image(
                image_path_raw.as_posix(),
                output_path.as_posix(),
                (width, height),
                self.content,
                self.title or "",
                self.author or "",
            )
            if result:
                logger.debug(f"Took {t.get_elapsed_time()} to process image: {output_path.as_posix()}")
                return output_path
            else:
                logger.error(f"Failed to process image: {output_path.as_posix()}")
                return None
        except Exception as e:
            logger.exception(f"Error processing image: {e}")
            return None


class Client(Base):
    """SQLAlchemy model representing a display client (e.g. an Inky Frame device).

    Attributes:
        id: Auto-incremented primary key.
        client_name: Unique human-readable name for the client.
        current_position: The client's current index within its shuffled quote sequence.
        default_width: Default display width in pixels for this client.
        default_height: Default display height in pixels for this client.
        sequence: One-to-many relationship to the client's shuffled quote order.
    """

    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    client_name: Mapped[str] = mapped_column(String, unique=True)
    current_position: Mapped[int] = mapped_column(Integer, default=-1)
    default_width: Mapped[int] = mapped_column(Integer, default=settings.default_width)
    default_height: Mapped[int] = mapped_column(Integer, default=settings.default_height)

    # Relationship to their specific shuffled deck
    sequence: Mapped[List["ClientSequence"]] = relationship(back_populates="client")


class ClientSequence(Base):
    """SQLAlchemy model mapping a client to a quote at a specific position in their shuffled deck.

    The composite primary key is ``(client_id, quote_id, position)``.

    Attributes:
        client_id: Foreign key to :class:`Client`.
        quote_id: Foreign key to :class:`Quote`.
        position: Zero-based index in the client's shuffled sequence.
        client: Back-reference to the owning :class:`Client`.
        quote: Reference to the associated :class:`Quote`.
    """

    __tablename__ = "client_sequences"

    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), primary_key=True)
    quote_id: Mapped[str] = mapped_column(ForeignKey("quotes.id"), primary_key=True)
    position: Mapped[int] = mapped_column(Integer, primary_key=True)

    client: Mapped["Client"] = relationship(back_populates="sequence")
    quote: Mapped["Quote"] = relationship()


# 2. The Engine Manager
class QuoteManager:
    """High-level manager for quote storage, client registration, and sequenced quote retrieval.

    Wraps a SQLAlchemy engine and session factory, providing convenience methods for the
    REST API and Notion sync workflows.

    Args:
        SQLAlchemy database URL.  Defaults to a local SQLite file ``quotes.db``.
    """

    def __init__(self, db_url: str = settings.database_url):
        self.db_url = db_url
        self.engine = create_engine(db_url)
        Base.metadata.create_all(self.engine)
        self._migrate_db()
        self.Session = sessionmaker(bind=self.engine)

    def _migrate_db(self):
        """Lightweight migration: add any new columns to existing tables."""
        insp = inspect(self.engine)
        if "clients" in insp.get_table_names():
            existing_cols = {col["name"] for col in insp.get_columns("clients")}
            with self.engine.begin() as conn:
                if "default_width" not in existing_cols:
                    conn.execute(
                        text(
                            "ALTER TABLE clients ADD COLUMN default_width"
                            f" INTEGER NOT NULL DEFAULT {settings.default_width}"
                        )
                    )
                    logger.info("Migrated clients table: added default_width column")
                if "default_height" not in existing_cols:
                    conn.execute(
                        text(
                            f"ALTER TABLE clients ADD COLUMN default_height"
                            f" INTEGER NOT NULL DEFAULT {settings.default_height}"
                        )
                    )
                    logger.info("Migrated clients table: added default_height column")

    def upsert_quote(self, quote_data: dict):
        """Insert a new quote or update an existing one.

        Args:
            quote_data: Dictionary whose keys match :class:`Quote` column names. Must include ``"id"`` at a minimum.
        """
        with self.Session() as session:
            stmt = select(Quote).where(Quote.id == quote_data["id"])
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

    def get_stats(self) -> dict:
        """Return database statistics.

        Returns:
            A dictionary with ``client_count``, ``quote_count``, and ``database_file`` keys.
        """
        try:
            with self.Session() as session:
                client_count = session.query(Client).count()
                quote_count = session.query(Quote).count()
        except Exception:
            client_count = -1
            quote_count = -1
        return {"client_count": client_count, "quote_count": quote_count, "database_file": self.db_url}

    def get_all_quote_ids(self) -> List[str]:
        """Return every quote ID currently stored in the database.

        Returns:
            A list of quote ID strings.
        """
        with self.Session() as session:
            return list(session.scalars(select(Quote.id)).all())

    def delete_quote(self, quote_id: str):
        """Delete a quote and all associated client-sequence entries.

        Args:
            quote_id: The ID of the quote to remove.
        """
        from sqlalchemy import delete

        with self.Session() as session:
            quote = session.get(Quote, quote_id)
            if quote:
                # Delete any client sequences referencing this quote
                session.execute(delete(ClientSequence).where(ClientSequence.quote_id == quote_id))

                session.delete(quote)
                session.commit()
                logger.info(f"Deleted quote {quote_id}")

    def register_client(self, client_name: str, width: Optional[int] = None, height: Optional[int] = None) -> Client:
        """Register a new client or return the existing one.

        When creating a new client a shuffled sequence of all current quotes is generated
        so that the client can immediately begin retrieving quotes.

        Args:
            client_name: Unique name identifying the client.
            width: Default display width in pixels.  Falls back to ``settings.default_width``.
            height: Default display height in pixels.  Falls back to ``settings.default_height``.

        Returns:
            The newly created or pre-existing :class:`Client` instance.
        """
        with self.Session() as session:
            # Check if client exists
            client = session.scalar(select(Client).where(Client.client_name == client_name))
            if client:
                # Ensure they have a sequence if they exist but somehow no sequence?
                # (Logic handled in sync_new_quotes, but effectively we assume if client exists, they might need sync)
                return client

            # Create new client with optional custom dimensions
            new_client = Client(
                client_name=client_name,
                default_width=width or settings.default_width,
                default_height=height or settings.default_height,
            )
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
        """Append any newly added quotes to the client's shuffled sequence.

        Quotes already present in the client's deck are skipped.  New quotes are shuffled
        and appended after the current last position.

        Args:
            client_name: The unique name of the client to sync.
        """
        with self.Session() as session:
            # 1. Get the client
            client = session.scalar(select(Client).where(Client.client_name == client_name))
            if not client:
                # Need to register first? Or just return
                return

            # 2. Find Quote IDs the client DOES NOT have in their sequence yet
            existing_quote_ids_stmt = select(ClientSequence.quote_id).where(ClientSequence.client_id == client.id)

            new_quotes_stmt = select(Quote.id).where(Quote.id.not_in(existing_quote_ids_stmt))
            new_quote_ids = list(session.scalars(new_quotes_stmt).all())

            if not new_quote_ids:
                return  # Everything is already synced

            # 3. Shuffle only the new quotes
            random.shuffle(new_quote_ids)

            # 4. Find the current max position for this client
            max_pos = session.scalar(
                select(func.max(ClientSequence.position)).where(ClientSequence.client_id == client.id)
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
        """Return the quote at a specific position in a client's shuffled sequence.

        Args:
            session: An active SQLAlchemy session.
            client: The :class:`Client` whose sequence to look up.
            position: Zero-based index in the client's sequence.

        Returns:
            The :class:`Quote` at the given position, or ``None`` if not found.
        """
        stmt = (
            select(Quote)
            .join(ClientSequence)
            .where(ClientSequence.client_id == client.id)
            .where(ClientSequence.position == position)
        )
        return session.scalar(stmt)

    def get_client(self, client_name: str) -> Optional[Client]:
        """Look up a client by its unique name.

        Args:
            client_name: The name to search for.

        Returns:
            The matching :class:`Client`, or ``None`` if no client has that name.
        """
        with self.Session() as session:
            return session.scalar(select(Client).where(Client.client_name == client_name))

    def add_client(self, client_name: str, width: Optional[int] = None, height: Optional[int] = None) -> Client:
        """Add a new client or return the existing one, with optional custom display dimensions.

        Intended for the REST API to pre-register clients before they connect to a quote
        endpoint.  Delegates to :meth:`register_client`.

        Args:
            client_name: Unique name identifying the client.
            width: Default display width in pixels.  Falls back to ``settings.default_width``.
            height: Default display height in pixels.  Falls back to ``settings.default_height``.

        Returns:
            The newly created or pre-existing :class:`Client` instance.
        """
        return self.register_client(client_name, width=width, height=height)

    def update_client(
        self,
        client_id: int,
        width: Optional[int] = None,
        height: Optional[int] = None,
        position: Optional[int] = None,
    ) -> Optional[Client]:
        """Update an existing client's default dimensions and/or current position.

        Only non-``None`` arguments are applied.

        Args:
            client_id: Primary key of the client to update.
            width: New default display width in pixels.
            height: New default display height in pixels.
            position: New current position in the quote rotation.

        Returns:
            The updated :class:`Client`, or ``None`` if no client with that ID exists.
        """
        with self.Session() as session:
            client = session.get(Client, client_id)
            if not client:
                return None
            if width is not None:
                client.default_width = width
            if height is not None:
                client.default_height = height
            if position is not None:
                client.current_position = position
            session.commit()
            # Expunge so the object is usable outside the session
            session.expunge(client)
            return client

    def get_quote(
        self,
        client_name: str,
        direction: QueryDirection,
        width: Optional[int] = None,
        height: Optional[int] = None,
    ) -> tuple[Optional[Quote], Client]:
        """Retrieve a quote for a client based on the requested navigation direction.

        On the very first connection (client does not exist yet), query-arg ``width``/``height``
        are persisted as the client's defaults.  On subsequent connections the stored defaults
        are used when no explicit values are provided.

        Args:
            client_name: Unique name identifying the requesting client.
            direction: Navigation direction — one of the :class:`QueryDirection` enum members
                       (``CURRENT``, ``FORWARD``, ``REVERSE``, ``RANDOM``).
            width: Optional display width override in pixels.
            height: Optional display height override in pixels.

        Returns:
            A ``(quote, client)`` pair.  ``quote`` is ``None`` when no quotes are available; ``client`` is ``None``
            when the client could not be found after registration.
        """

        # Ensure client exists and is synced – pass width/height so that a
        # brand-new client stores them as defaults.
        self.register_client(client_name, width=width, height=height)
        self.sync_new_quotes(client_name)

        with self.Session() as session:
            client = session.scalar(select(Client).where(Client.client_name == client_name))
            if not client:
                return None, None

            # Get total count of quotes for this client
            count_stmt = select(func.count(ClientSequence.quote_id)).where(ClientSequence.client_id == client.id)
            total_count = session.scalar(count_stmt) or 0

            if total_count == 0:
                return None, client

            current_pos = client.current_position
            new_pos = current_pos

            if direction == QueryDirection.CURRENT:
                # If -1 (just started), move to 0
                if current_pos < 0:
                    new_pos = 0
            elif direction == QueryDirection.FORWARD:
                new_pos = current_pos + 1
                if new_pos >= total_count:
                    new_pos = 0  # Loop back to start
            elif direction == QueryDirection.REVERSE:
                new_pos = current_pos - 1
                if new_pos < 0:
                    new_pos = total_count - 1  # Loop back to end
            elif direction == QueryDirection.RANDOM:
                new_pos = random.randint(0, total_count - 1)

            # Update client position
            client.current_position = new_pos
            session.add(client)
            session.commit()

            return self._get_quote_at_position(session, client, new_pos), client
