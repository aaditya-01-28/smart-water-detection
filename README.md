# 🌊 Smart Water Detection System

This project uses a YOLOv8 model to monitor CCTV camera feeds in real-time, detect water accumulation on industrial floors, and send automated alerts via Email and WhatsApp. It also logs events to Google Sheets and stores images on Google Drive.


---

## ✨ Features

- **Real-Time Detection**: Uses a custom-trained YOLOv8 model to identify water and floor areas.
- **Automated Alerts**: Sends notifications with images via Email and WhatsApp when water percentage exceeds a set threshold.
- **Cloud Integration**: Logs cycle completions to Google Sheets and uploads images to specific Google Drive folders.
- **Configurable**: Camera URLs, alert thresholds, and recipient lists can be easily configured through text files.
- **Secure**: Manages all sensitive credentials and API keys using environment variables, keeping them out of the source code.

---

## 🛠️ Installation

1.  **Clone the repository:**
    ```bash
    git clone [https://github.com/your-username/smart-water-detection.git](https://github.com/your-username/smart-water-detection.git)
    cd smart-water-detection
    ```

2.  **Create a virtual environment and activate it:**
    ```bash
    python -m venv venv
    # On Windows
    .\venv\Scripts\activate
    # On macOS/Linux
    source venv/bin/activate
    ```

3.  **Install the required dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

---

## ⚙️ Configuration

1.  **Set up Google Credentials**:
    - Follow the Google Cloud documentation to create a service account.
    - Download the JSON key file and save it in the root of the project as `credentials.json`.
    - Enable the Google Drive API and Google Sheets API for your project.
    - Share your Google Sheet and Google Drive folders with the `client_email` found in your `credentials.json` file.

2.  **Create your environment file**:
    - Copy the example file: `cp .env.example .env`
    - Open the `.env` file and fill in all the required values (your camera credentials, Google Drive folder IDs, email details, etc.).

3.  **Update configuration files**:
    - Add your camera stream URLs to `config/link.txt`.
    - Add recipient email addresses to `config/receiver_emails.txt`.
    - Set the detection percentage in `config/water_threshold.txt`.

---

## ▶️ Running the Application

Once everything is configured, run the main script from the root directory:

```bash
python src/main.py
```
The script will start monitoring the camera feeds and will send alerts if water is detected.