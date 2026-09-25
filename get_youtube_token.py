import os
from dotenv import load_dotenv
from google_auth_oauthlib.flow import InstalledAppFlow

# Fix for common OAuth issues over localhost
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'

# Load variables from the .env file
load_dotenv()

CLIENT_ID = os.getenv("YOUTUBE_CLIENT_ID")
CLIENT_SECRET = os.getenv("YOUTUBE_CLIENT_SECRET")

if not CLIENT_ID or not CLIENT_SECRET:
    print("Error: YOUTUBE_CLIENT_ID and/or YOUTUBE_CLIENT_SECRET are missing from your .env file.")
    print("Please make sure they are set correctly and try again.")
    exit(1)

client_config = {
    "web": {
        "client_id": CLIENT_ID.strip(),
        "client_secret": CLIENT_SECRET.strip(),
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": ["http://localhost:8080/"]
    }
}

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

def get_authenticated_service():
    print(f"Using Client ID from .env: {CLIENT_ID[:15]}...")
    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    
    # We must explicitly set the redirect URI here for the manual copy-paste flow
    flow.redirect_uri = "http://localhost:8080/"
    
    # Generate the authorization URL
    auth_url, _ = flow.authorization_url(prompt='consent', access_type='offline')
    
    print("\n1. Please go to this URL in your browser:")
    print(f"\n{auth_url}\n")
    print("2. Authorize the application. After you accept, your browser will be redirected to an error page (like 'This site can’t be reached' or a localhost page).")
    print("3. Copy the ENTIRE URL from your browser's address bar and paste it below.\n")
    
    redirect_response = input("Paste the full redirect URL here: ").strip()
    
    # Fetch the token using the pasted URL
    flow.fetch_token(authorization_response=redirect_response)
    credentials = flow.credentials
    
    print("\n--- NEW REFRESH TOKEN ---")
    print(credentials.refresh_token)
    print("-------------------------\n")
    print("Please update your secrets:")
    print("1. Update YOUTUBE_REFRESH_TOKEN in your .env")
    print("2. Update both YOUTUBE_CLIENT_SECRET and YOUTUBE_REFRESH_TOKEN in GitHub Actions.")

if __name__ == '__main__':
    get_authenticated_service()
