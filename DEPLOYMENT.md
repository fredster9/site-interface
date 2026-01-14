# Streamlit Cloud Deployment Guide

## ✅ What's Been Done

1. **Secrets Migration**: Code now uses Streamlit secrets instead of local JSON file
   - Falls back to `openai_secrets.json` for local development
   - Uses `st.secrets` for Streamlit Cloud

2. **Security**: 
   - All secrets files are in `.gitignore`
   - No API keys will be committed to git

3. **Files Ready for Deployment**:
   - `via_web_app.py` - Main app (updated for Streamlit secrets)
   - `requirements.txt` - Dependencies
   - `.streamlit/config.toml` - Streamlit configuration
   - `README.md` - Updated documentation
   - `.gitignore` - Excludes all secrets

## 🚀 Deployment Steps

### 1. Commit and Push to GitHub

```bash
# Review what will be committed
git status

# Commit the changes
git commit -m "Initial commit: Via web app with Streamlit Cloud support"

# Push to GitHub (if this is the first push)
git push -u origin main

# Or if you already have a main branch
git push origin main
```

### 2. Deploy to Streamlit Cloud

1. Go to [share.streamlit.io](https://share.streamlit.io)
2. Click "New app"
3. Connect your GitHub repository: `fredster9/site-interface`
4. Set:
   - **Main file path**: `via_web_app.py`
   - **App URL**: (choose your preferred URL)

### 3. Add Secrets in Streamlit Cloud

1. In your app settings, go to **"Secrets"**
2. Add the following:

```toml
[openai]
api_key = "sk-proj-your-actual-api-key-here"

[google_sheets]
spreadsheet_id = "your-spreadsheet-id-here"
sheet_name = "Q&A Log"
service_account_json = '''
{
  "type": "service_account",
  "project_id": "your-project-id",
  "private_key_id": "your-key-id",
  "private_key": "-----BEGIN PRIVATE KEY-----\\n...\\n-----END PRIVATE KEY-----\\n",
  "client_email": "your-service-account@your-project.iam.gserviceaccount.com",
  "client_id": "your-client-id",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token",
  "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
  "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/...",
  "universe_domain": "googleapis.com"
}
'''
```

**OR** alternatively for OpenAI:

```toml
OPENAI_API_KEY = "sk-proj-your-actual-api-key-here"
```

**Google Sheets Setup:**
1. Create a Google Sheet for logging
2. Create a Google Cloud service account (or use existing)
3. Download the service account JSON key
4. Share the Google Sheet with the service account email (give Editor access)
5. Copy the spreadsheet ID from the Google Sheet URL
6. Paste the service account JSON into the secrets (as shown above)

### 4. Deploy!

Click "Deploy" and your app will be live!

## 🔒 Security Notes

- ✅ No secrets are committed to git
- ✅ `.gitignore` excludes all secret files
- ✅ Streamlit Cloud secrets are encrypted
- ✅ Local `openai_secrets.json` is ignored by git

## 📝 Local Development

For local development, you can still use `openai_secrets.json`:

```json
{
  "openai_api_key": "your-key-here"
}
```

The app will automatically use Streamlit secrets if available, or fall back to the local file.

## 🐛 Troubleshooting

- **"OpenAI API key not found"**: Make sure you've added secrets in Streamlit Cloud
- **Import errors**: Check that `requirements.txt` has all dependencies
- **Cache issues**: The cache will rebuild automatically on first run in the cloud
