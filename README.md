# Ditto

Ditto is a personal project designed to display quotes from a Notion database onto an eInk display. It renders quotes into formatted images, specifically optimized for display on a framed eInk display.

## Inspiration

My wife has a Notion database of quotes from her favorite books. I thought it would be fun to display them on an eInk display. I picked up an [Inky Frame](https://shop.pimoroni.com/products/inky-frame-7-3?variant=40541882056787) which has very limited RAM (520kb total) which ruled out local processing. I could have pre-rendered all the quotes but I wanted it to automatically update when new ones were added or old ones removed. With that in mind I set out on designing a service that I could run on my home server which would render and serve the images to the Inky Frame. I then used a wooden picture frame with some 3D printed parts to house the Inky Frame. (Pictures to come)

## Features

* **Notion Integration**: Automatically syncs quotes from a specified Notion database.
* **eInk Optimization**: Generates high-contrast images suitable for eInk displays. Also capable of dithering the image to a custom platte (see `resources/palette_7.png`) but I've found the device does a better job at this.
* **Smart Scheduling**: Includes a daily background task to keep the local database in sync with Notion.
* **REST API**: Powered by FastAPI, providing endpoints to fetch the current, next, previous, or random quotes.
* **Client Tracking**: Maintains state for different clients, ensuring a consistent rotation of quotes in which the order for each client is randomized. This way if I build more of these they will show different quotes in different orders.

## Tech Stack

* **Language**: Python 3.12+
* **Web Framework**: FastAPI
* **Image Processing**: Pillow (PIL)
* **Database**: SQLAlchemy w/ SQLite
* **Notion API**: `notion-client`
* **Deployment**: Docker

## API Endpoints

* `GET /`: Returns server status and statistics.
* `GET /current`: Returns the current quote image for the client.
* `GET /next`: Advances to and returns the next quote.
* `GET /previous`: Moves backwards to and returns the previous quote.
* `GET /random`: Returns a random quote and moves to that position.
* `POST /clients`: Pre-register a new client with optional default `width` and `height`.
* `PATCH /clients/{client_id}`: Update a client's default `width`, `height`, and/or `position`.
* `GET /clients`: List all registered clients and their stored defaults.
* `GET /health`: Health check endpoint.

`current`, `next`, `previous`, and `random` all accept the following query args:

* `client_override` — specify the client name. Useful for testing or manually controlling the rotation for a specific client.
* `width` / `height` — override the image dimensions. On a client's first connection these values are stored as the client's defaults. On subsequent connections the stored defaults are used when no explicit values are provided.

### Client Registration

Clients can be pre-registered via `POST /clients` with a JSON body:

```json
{
  "client_name": "my-inky-frame",
  "width": 800,
  "height": 480
}
```

If `width` or `height` are omitted the global defaults (`800×480`) are used. Clients are also auto-registered on their first request to any quote endpoint.

### Updating a Client

Use `PATCH /clients/{client_id}` to update a client's settings. All fields are optional — only supplied fields are modified:

```json
{
  "width": 1024,
  "height": 600,
  "position": 0
}
```

## Inky Frame Client (Ditto View)

The `src/ditto_view` directory contains the Python code specifically designed to run on the Pimoroni Inky Frame (Raspberry Pi Pico2 W based). This code fetches the images from the Ditto server and displays them.

### Key Files

* `main.py`: The entry point for the MicroPython environment. It connects to Wi-Fi, fetches the image, and handles deep sleep to conserve battery.
* `inky_frame.py`: Contains the logic for interacting with the Inky Frame hardware, including initializing the display and drawing the image.
* `inky_helper.py`: Helper functions for network connectivity and power management.
* `secrets.py`: A template file for your Wi-Fi credentials (`WIFI_SSID` and `WIFI_PASSWORD`). You will need to fill this in before deploying to the device.

### Deployment

To deploy this code to your Inky Frame:

1. Connect your Inky Frame to your computer via USB.
2. Copy the files from `src/ditto_view` to the root of the Inky Frame's storage.
3. Update `secrets.py` on the device with your actual Wi-Fi credentials.

## Getting Started

### Notion Database

Requires a Notion database with the following configuration along with an API key and database ID.

| Property    | Type        | Contents                                        |
|-------------|-------------|-------------------------------------------------|
| Page Name   | NA          | The quote                                       |
| TITLE       | String      | The book title                                  |
| AUTHOR      | String      | The author name                                 |
| DISPLAY     | Checkbox    | Uncheck to remove from service                  |
| Image Block | NA          | The first image block is used as the background |

### Prerequisites

* Python 3.12 or higher
* Docker (optional, for containerized deployment)
* A Notion API Key and Database ID

### Running Locally

1. **Clone the repository**:

    ```bash
    git clone https://github.com/david2777/ditto.git
    cd ditto
    ```

2. **Set up environment variables**:
    Create a `.env` file in the root directory with your Notion credentials and other settings.

    ```env
    NOTION_KEY=your_notion_api_key
    NOTION_DATABASE_ID=your_notion_database_id
    ```

3. **Install UV**

    ```bash
    pip install uv
    ```

4. **Install dependencies**:

    ```bash
    uv pip install -e .
    ```

5. **Run the server**:

    ```bash
    uvicorn ditto.main:app --reload
    ```
