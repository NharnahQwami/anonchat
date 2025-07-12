# Anonymous Chat

A privacy-first, ephemeral chat application built with FastAPI. No registration required, messages are stored only in memory and auto-deleted after 30 minutes. Supports password-protected rooms, end-to-end encryption (E2E), and self-destructing messages.

## Features

- Anonymous chat rooms (no signup)
- Password protection for rooms
- End-to-end encryption (E2E) in browser
- Self-destructing messages
- Ephemeral: messages and rooms auto-delete after inactivity
- Live stats dashboard

## Getting Started

### Prerequisites

- Python 3.8+
- [pip](https://pip.pypa.io/en/stable/)

### Installation

1. Clone the repository:

    ```sh
    git clone https://github.com/yourusername/anonchat.git
    cd anonchat
    ```

2. Create a virtual environment and activate it:

    ```sh
    python -m venv env
    source env/bin/activate
    ```

3. Install dependencies:

    ```sh
    pip install -r requirements.txt
    ```

### Running the Application

Start the FastAPI server:

```sh
uvicorn main:app --host 0.0.0.0 --port 8000
```

Open [http://localhost:8000](http://localhost:8000) in your browser.

### Docker (Optional)

Build and run with Docker:

```sh
docker build -t anonchat .
docker run -p 8000:8000 anonchat
```

## Project Structure

```
main.py              # FastAPI backend
requirements.txt     # Python dependencies
static/              # Frontend HTML/CSS/JS
    index.html
    room.html
```

## Usage

- Go to the homepage and create a new chat room.
- Optionally set a password for extra privacy.
- Share the room link with your contact.
- Messages are not stored permanently and will be deleted when the chat ends or after 30 minutes of inactivity.
