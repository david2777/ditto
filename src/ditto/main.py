from loguru import logger
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse

from ditto import constants, database, secrets
from ditto.utilities.timer import Timer

notion_db = database.NotionDatabaseManager(secrets.NOTION_DATABASE_ID)

app = FastAPI()


async def _process_quote(quote_item: database.NotionQuote):
    await quote_item.process_image()

    response = FileResponse(quote_item.image_path_processed.as_posix(), media_type="image/jpeg")
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.get("/")
async def root_endpoint(request: Request):
    logger.info(f"request: {request.method} {request.url}")
    response = {"message": f"Ditto {constants.VERSION}"}
    logger.info(f"response: {response}")
    return response


@app.get("/next")
async def next_endpoint(request: Request):
    t = Timer()
    logger.info(f"request: {request.method} {request.url}")

    quote_item = await notion_db.get_next_item()
    response = await _process_quote(quote_item)
    logger.info(f'response: "{quote_item.image_path_processed.as_posix()}" generated in {t.get_elapsed_time()} seconds')
    return response


@app.get("/previous")
async def previous_endpoint(request: Request):
    t = Timer()
    logger.info(f"request: {request.method} {request.url}")

    quote_item = await notion_db.get_previous_item()
    response = await _process_quote(quote_item)
    logger.info(f'response: "{quote_item.image_path_processed.as_posix()}" generated in {t.get_elapsed_time()} seconds')
    return response


@app.get("/random")
async def random_endpoint(request: Request):
    t = Timer()
    logger.info(f"request: {request.method} {request.url}")

    quote_item = await notion_db.get_random_item()
    response = await _process_quote(quote_item)
    logger.info(f'response: "{quote_item.image_path_processed.as_posix()}" generated in {t.get_elapsed_time()} seconds')
    return response
