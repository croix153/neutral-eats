#!/usr/bin/env python3
"""Check Overture ingestion progress"""
import paramiko
import time

host = '74.207.224.129'
username = 'minerva'
password = 'REDACTED'

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(host, username=username, password=password, timeout=20)

print('📊 Overture Ingestion Progress')
print('='*50)

# Check if PHP process is running
stdin, stdout, stderr = ssh.exec_command('ps aux | grep ingestion_overture.php | grep -v grep')
if stdout.read().decode().strip():
    print('✅ PHP Overture ingestion is RUNNING')
else:
    print('⏸️ PHP Overture ingestion has completed or stopped')

# Show the PHP log
print('\n📝 Overture Ingestion Log:')
stdin, stdout, stderr = ssh.exec_command('tail -50 /var/www/html/minerva/data/overture_ingestion.log 2>/dev/null || echo "No log found"')
log_content = stdout.read().decode()
print(log_content)

# If completed, show final stats
if 'Ingestion complete' in log_content:
    print('\n📈 Final Database Stats:')
    stdin, stdout, stderr = ssh.exec_command(
        'mysql -u neutraleats_user -pneutraleats_pass neutraleats -e "SELECT source, COUNT(*) FROM venues GROUP BY source;"'
    )
    print(stdout.read().decode())
    
    print('\n🎯 Orlando Area Count:')
    stdin, stdout, stderr = ssh.exec_command(
        'mysql -u neutraleats_user -pneutraleats_pass neutraleats -e "SELECT COUNT(*) FROM venues WHERE lat BETWEEN 28.2 AND 28.8 AND lng BETWEEN -81.6 AND -81.1;"'
    )
    print(stdout.read().decode())

ssh.close()
