import os
import time
import cv2
import numpy as np
import pyautogui
import keyboard
import smtplib
import win32clipboard
import requests
from io import BytesIO
from PIL import Image
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from ultralytics import YOLO
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from requests.auth import HTTPDigestAuth
from dotenv import load_dotenv

# --- Load Environment Variables ---
# This securely loads the secrets from your .env file
load_dotenv()

# --- Global Variables & Configuration ---
screenshot_index = 0

# Credentials for camera (loaded from .env)
username = os.getenv("CAMERA_USER")
password = os.getenv("CAMERA_PASS")

# Google API Credentials (loaded from .env)
SERVICE_ACCOUNT_FILE = os.getenv("SERVICE_ACCOUNT_FILE")
SHEET_ID = os.getenv("SHEET_ID")
MAIN_FOLDER_ID = os.getenv("MAIN_FOLDER_ID")
DETECTED_FOLDER_ID = os.getenv("DETECTED_FOLDER_ID")
SCOPES_DRIVE = ['https://www.googleapis.com/auth/drive.file']
SCOPES_SHEETS = ["https://www.googleapis.com/auth/spreadsheets"]

# Email configuration (loaded from .env)
SENDER_EMAIL = os.getenv("SENDER_EMAIL")
APP_PASSWORD = os.getenv("APP_PASSWORD")

# WhatsApp configuration (loaded from .env)
WHATSAPP_NAME = os.getenv("WHATSAPP_NAME")

# --- Initialize Services ---
# Google Drive & Sheets
creds_drive = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES_DRIVE)
creds_sheets = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES_SHEETS)
drive_service = build('drive', 'v3', credentials=creds_drive)
sheets_service = build("sheets", "v4", credentials=creds_sheets)

# Load the YOLO model
model = YOLO("models/best.pt")

# Define paths (using relative paths for portability)
screenshot_folder = "screenshots"
os.makedirs(screenshot_folder, exist_ok=True)

# Read receiver emails from file
def load_emails(file_path):
    with open(file_path, "r") as file:
        return [line.strip() for line in file.readlines() if line.strip()]

RECEIVER_EMAILS = load_emails("config/receiver_emails.txt")

# Read water threshold from file
def load_water_threshold(file_path):
    try:
        with open(file_path, "r") as file:
            return int(file.read().strip())
    except Exception as e:
        print(f"❌ Error reading water threshold: {e}")
        return 15  # Default threshold

WATER_THRESHOLD_FILE = "config/water_threshold.txt"
WATER_THRESHOLD = load_water_threshold(WATER_THRESHOLD_FILE)

# Load URLs from file
def load_urls(file_path):
    with open(file_path, "r") as file:
        return [line.strip() for line in file if line.strip()]

urls = load_urls("config/link.txt")

# Track URLs where water was detected to manage cooldown
water_detected_urls = {}

# --- Core Functions ---

def fetch_camera_image(url, save_dir):
    """Fetches an image from a camera using Digest Auth and saves it locally."""
    global image_index
    filename = f"camera_capture_{image_index % 10}.jpg"  # Overwrite the last 10 captures
    image_path = os.path.join(save_dir, filename)

    try:
        response = requests.get(url, auth=HTTPDigestAuth(username, password), timeout=10)
        if response.status_code == 200:
            with open(image_path, "wb") as f:
                f.write(response.content)
            print(f"📸 Image saved from {url} as {filename}")
            image_index += 1
            return image_path
        else:
            print(f"❌ Failed to fetch image from {url}. Status: {response.status_code}")
    except Exception as e:
        print(f"❌ Error fetching image from {url}: {e}")
    return None

def update_sheet():
    """Updates a specific cell range in Google Sheets with a timestamp."""
    try:
        sheet = sheets_service.spreadsheets()
        current_time = time.strftime("%Y-%m-%d %H:%M:%S")
        values = [["Last Cycle Completed", current_time]]
        body = {'values': values}
        result = sheet.values().update(
            spreadsheetId=SHEET_ID,
            range="Sheet1!A2:B2",
            valueInputOption="RAW",
            body=body
        ).execute()
        print(f"✅ Google Sheets Updated with timestamp: {current_time}")
    except Exception as e:
        print(f"❌ Google Sheets Error: {e}")

def upload_file_to_drive(file_path, folder_id):
    """Uploads a file to a specified Google Drive folder."""
    try:
        file_metadata = {'name': os.path.basename(file_path), 'parents': [folder_id]}
        media = MediaFileUpload(file_path, mimetype='image/jpeg', resumable=True)
        file = drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id'
        ).execute()
        return file.get('id')
    except Exception as e:
        print(f"❌ Upload to Google Drive failed: {e}")
        return None

def detect_floor_and_water(image):
    """Processes an image with the YOLO model to find floor and water areas."""
    results = model(image)
    floor_mask = np.zeros(image.shape[:2], dtype=np.uint8)
    water_mask = np.zeros(image.shape[:2], dtype=np.uint8)
    
    for result in results:
        if result.boxes and result.masks:
            classes = result.boxes.cls
            for i, mask_points in enumerate(result.masks.xy):
                class_id = int(classes[i].item())
                contour = np.array(mask_points, dtype=np.int32)
                if class_id == 0:  # Floor
                    cv2.fillPoly(floor_mask, [contour], 255)
                elif class_id == 1:  # Water
                    cv2.fillPoly(water_mask, [contour], 255)
    
    floor_area = np.sum(floor_mask == 255)
    water_area = np.sum(water_mask == 255)
    return floor_mask, water_mask, floor_area, water_area

def process_screenshot(image_path):
    """Analyzes a captured image for water and triggers alerts if the threshold is exceeded."""
    image = cv2.imread(image_path)
    if image is None:
        print(f"❌ Could not read image from path: {image_path}")
        return None

    _, _, floor_area, water_area = detect_floor_and_water(image)
    water_percentage = (water_area / floor_area) * 100 if floor_area > 0 else 0
    print(f"🔍 Water Percentage: {water_percentage:.2f}% (Threshold: {WATER_THRESHOLD}%)")

    if water_percentage > WATER_THRESHOLD:
        # Save a new, unique image for this specific alert
        timestamp = int(time.time())
        alert_image_filename = f"detection_alert_{timestamp}.jpg"
        alert_image_path = os.path.join(screenshot_folder, alert_image_filename)
        cv2.imwrite(alert_image_path, image)

        # Upload the alert image to the "detected" folder on Google Drive
        drive_file_id = upload_file_to_drive(alert_image_path, DETECTED_FOLDER_ID)
        if drive_file_id:
            print(f"🚨 Water detected! Image uploaded to DETECTED folder. File ID: {drive_file_id}")
        return alert_image_path
    
    return None

def copy_image_to_clipboard(image_path):
    """Copies an image file to the system clipboard (Windows)."""
    try:
        image = Image.open(image_path)
        output = BytesIO()
        image.convert('RGB').save(output, 'BMP')
        data = output.getvalue()[14:]
        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32clipboard.CF_DIB, data)
        win32clipboard.CloseClipboard()
    except Exception as e:
        print(f"❌ Failed to copy image to clipboard: {e}")

def send_email_with_image(image_path):
    """Sends an email with an attached image to all configured recipients."""
    msg = MIMEMultipart()
    msg['From'] = SENDER_EMAIL
    msg['To'] = ", ".join(RECEIVER_EMAILS)
    msg['Subject'] = "🚨 Water Detected!"
    msg.attach(MIMEText("Water has been detected on the floor. Please see the attached image.", 'plain'))
    
    with open(image_path, "rb") as img_file:
        img = MIMEImage(img_file.read(), name=os.path.basename(image_path))
        msg.attach(img)
    
    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(SENDER_EMAIL, APP_PASSWORD)
        server.sendmail(SENDER_EMAIL, RECEIVER_EMAILS, msg.as_string())
        server.quit()
        print("✅ Email sent successfully!")
    except Exception as e:
        print(f"❌ Email Error: {e}")

def send_whatsapp_message():
    """Automates sending a WhatsApp message with the image from the clipboard."""
    try:
        keyboard.press_and_release('win')
        time.sleep(2)
        keyboard.write('WhatsApp')
        time.sleep(3)
        keyboard.press_and_release('enter')
        time.sleep(8)
        pyautogui.hotkey("ctrl", "f")
        time.sleep(1)
        keyboard.write(WHATSAPP_NAME)
        time.sleep(2)
        pyautogui.hotkey("down")
        pyautogui.hotkey("enter")
        time.sleep(2)
        pyautogui.write("🚨 Water has been detected! See the attached image.")
        pyautogui.hotkey('ctrl', 'v')
        time.sleep(2)
        pyautogui.hotkey('enter')
        time.sleep(2)
        print("✅ WhatsApp message sent successfully!")
        pyautogui.hotkey('alt', 'f4') # Close WhatsApp window
        time.sleep(1)
    except Exception as e:
        print(f"❌ WhatsApp automation error: {e}")

# --- Main Execution Loop ---
if __name__ == "__main__":
    while True:
        current_time = time.time()
        for url in urls:
            if url in water_detected_urls:
                last_checked = water_detected_urls[url]
                if current_time - last_checked < 2700:  # 45-minute cooldown
                    print(f"⏳ Skipping {url}, in cooldown. Last alert was {int((current_time - last_checked) / 60)} minutes ago.")
                    continue

            image_path = fetch_camera_image(url, screenshot_folder)
            if image_path:
                alert_image = process_screenshot(image_path)
                if alert_image:
                    water_detected_urls[url] = current_time  # Update cooldown timestamp
                    copy_image_to_clipboard(alert_image)
                    send_email_with_image(alert_image)
                    send_whatsapp_message()
                    print(f"🚨 Alert process completed for {url}.")

        update_sheet()
        print("🔄 Completed one full cycle. Pausing for 10 seconds...")
        time.sleep(10)