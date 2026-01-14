# Google Sheets Setup Guide

## Quick Setup Steps

### 1. Create a Google Sheet
1. Go to [Google Sheets](https://sheets.google.com)
2. Create a new spreadsheet
3. Name it something like "Via Q&A Log"
4. Copy the **Spreadsheet ID** from the URL:
   - URL format: `https://docs.google.com/spreadsheets/d/SPREADSHEET_ID/edit`
   - The `SPREADSHEET_ID` is the long string between `/d/` and `/edit`

### 2. Create a Google Cloud Service Account
1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a new project (or use existing)
3. Enable **Google Sheets API** and **Google Drive API**:
   - Go to "APIs & Services" → "Library"
   - Search for "Google Sheets API" → Enable
   - Search for "Google Drive API" → Enable
4. Create a Service Account:
   - Go to "APIs & Services" → "Credentials"
   - Click "Create Credentials" → "Service Account"
   - Give it a name (e.g., "via-qa-logger")
   - Click "Create and Continue"
   - Skip role assignment (click "Continue")
   - Click "Done"
5. Create a Key:
   - Click on the service account you just created
   - Go to "Keys" tab
   - Click "Add Key" → "Create new key"
   - Choose "JSON"
   - Download the JSON file

### 3. Share the Google Sheet
1. Open the JSON file you downloaded
2. Find the `client_email` field (looks like: `something@project-id.iam.gserviceaccount.com`)
3. Open your Google Sheet
4. Click "Share" button
5. Add the service account email
6. Give it **Editor** permissions
7. Click "Send"

### 4. Add to Streamlit Secrets
1. Open the JSON file you downloaded
2. Copy the entire contents
3. In Streamlit Cloud, go to your app → Settings → Secrets
4. Add:

```toml
[google_sheets]
spreadsheet_id = "your-spreadsheet-id-here"
sheet_name = "Q&A Log"
service_account_json = '''
{
  "type": "service_account",
  "project_id": "...",
  "private_key_id": "...",
  "private_key": "...",
  "client_email": "...",
  ...
}
'''
```

**Important:** 
- Replace `your-spreadsheet-id-here` with your actual spreadsheet ID
- Paste the entire JSON content between the triple quotes
- The `sheet_name` is optional (defaults to "Q&A Log")

### 5. Test It!
Ask a question in the app and check your Google Sheet - you should see the Q&A appear!

## Fallback to CSV

If Google Sheets isn't configured, the app will automatically fall back to saving to `qa_log.csv` locally. This works for both local development and Streamlit Cloud.

## Troubleshooting

- **"Permission denied"**: Make sure you shared the sheet with the service account email
- **"Spreadsheet not found"**: Check that the spreadsheet ID is correct
- **"API not enabled"**: Make sure Google Sheets API and Drive API are enabled in Google Cloud Console
