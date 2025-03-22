from loguru import logger
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse

from ditto import constants, database, secrets
from ditto.utilities.timer import Timer

notion_db = database.NotionDatabaseManager(secrets.NOTION_DATABASE_ID)

app = FastAPI()


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

    item = await notion_db.get_next_item()
    await item.process_image()

    logger.info(f'response: "{item.image_path_processed.as_posix()}" generated in {t.get_elapsed_time()} seconds')
    return FileResponse(item.image_path_processed.as_posix(), media_type="image/jpeg")


@app.get("/previous")
async def previous_endpoint(request: Request):
    t = Timer()
    logger.info(f"request: {request.method} {request.url}")

    item = await notion_db.get_previous_item()
    await item.process_image()

    logger.info(f'response: "{item.image_path_processed.as_posix()}" generated in {t.get_elapsed_time()} seconds')
    return FileResponse(item.image_path_processed.as_posix(), media_type="image/jpeg")
