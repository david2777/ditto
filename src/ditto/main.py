from pathlib import Path

from loguru import logger
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse

from ditto import image_processing, constants
from ditto.utilities.timer import Timer

app = FastAPI()

@app.get("/")
async def root(request: Request):
    logger.info(f"request: {request.method} {request.url}")
    response = {"message": f"Ditto {constants.VERSION}"}
    logger.info(f"response: {response}")
    return response

@app.get("/random")
async def random(request: Request):
    t = Timer()
    logger.info(f"request: {request.method} {request.url}")
    # Get quote
    image_path = Path("/Users/david/Documents/git/ditto/test_images/resize/1920x1920.png")
    out_image_path = image_path.with_stem('output')  # TODO: tempdir?
    quote = 'Hello World! This is my test quote for my test app.'
    title = 'My Title'
    author = 'David Lee-DuVoisin'

    image = image_processing.DittoImage(image_path.as_posix())
    image.initial_resize()
    image.blur()
    image.add_text(quote, title, author)
    image.write(out_image_path.as_posix())
    logger.info(f'response: "{out_image_path.as_posix()}" generated in {t.get_elapsed_time()} seconds')
    return FileResponse(out_image_path.as_posix(), media_type="image/png")
