#!/usr/bin/env python3
"""Add Yelp API key to ingestion pipeline"""
import paramiko
import sys

host = '74.207.224.129'
username = 'minerva'
password = 'REDACTED'

if len(sys.argv) < 2:
    print("Usage: python3 add_yelp_key.py <your_yelp_api_key>")
    print("\nTo get a Yelp API key:")
    print("1. Go to https://www.yelp.com/developers")
    print("2. Sign in and create a new app")
    print("3. Copy the API Key (not the Client ID)")
    print("4. Run: python3 add_yelp_key.py YOUR_KEY_HERE")
    sys.exit(1)

yelp_key = sys.argv[1]

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(host, username=username, password=password, timeout=20)
print('✅ Connected to Minerva server')

# Update the file with the API key
stdin, stdout, stderr = ssh.exec_command(
    f"sed -i \"s/YELP_API_KEY = None/YELP_API_KEY = 'REDACTED'/\" /var/www/html/minerva/ingestion_pipeline.py"
)
print('✅ Yelp API key added to pipeline')

# Verify it was set
stdin, stdout, stderr = ssh.exec_command(
    "grep 'YELP_API_KEY' /var/www/html/minerva/ingestion_pipeline.py | head -1"
)
result = stdout.read().decode().strip()
if 'None' not in result:
    print(f'✅ Verified: {result}')
    print('\n🎉 Yelp integration is now active!')
    print('   The pipeline will use Yelp to fill gaps where Overture/OSM coverage is low.')
    print('   Next run will include Yelp for low-coverage areas.')
else:
    print('⚠️ Key may not have been set correctly')

ssh.close()
