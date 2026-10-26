#!/usr/bin/env python3
"""Check coverage across Central Florida to find sparse areas"""
import paramiko

host = '74.207.224.129'
username = 'minerva'
password = 'REDACTED'

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(host, username=username, password=password, timeout=30)

print("📊 Central Florida Coverage Analysis")
print("="*60)

# Check various areas
areas = [
    ("Lake Mary", 28.73, 28.78, -81.36, -81.30),
    ("Sanford", 28.78, 28.83, -81.32, -81.25),
    ("Longwood", 28.68, 28.73, -81.38, -81.30),
    ("Altamonte Springs", 28.65, 28.70, -81.42, -81.35),
    ("Winter Springs", 28.68, 28.73, -81.32, -81.25),
    ("Oviedo", 28.65, 28.72, -81.25, -81.18),
    ("Kissimmee", 28.28, 28.35, -81.45, -81.38),
    ("Celebration", 28.30, 28.33, -81.55, -81.52),
]

for name, lat_min, lat_max, lng_min, lng_max in areas:
    cmd = f'''mysql -u neutraleats_user -pneutraleats_pass neutraleats -e "SELECT COUNT(*) FROM venues WHERE lat BETWEEN {lat_min} AND {lat_max} AND lng BETWEEN {lng_min} AND {lng_max};"'''
    stdin, stdout, stderr = ssh.exec_command(cmd)
    count = stdout.read().decode().strip().split('\n')[-1]
    status = "🟢 Good" if int(count) > 100 else "🟡 Okay" if int(count) > 50 else "🔴 Sparse"
    print(f"{name:20} {count:>6} venues {status}")

# Check overall stats
print("\n" + "="*60)
print("📈 Overall Stats:")

cmd = '''mysql -u neutraleats_user -pneutraleats_pass neutraleats -e "SELECT source, COUNT(*) FROM venues GROUP BY source;"'''
stdin, stdout, stderr = ssh.exec_command(cmd)
print(stdout.read().decode())

cmd = '''mysql -u neutraleats_user -pneutraleats_pass neutraleats -e "SELECT COUNT(*) as 'Total Venues' FROM venues;"'''
stdin, stdout, stderr = ssh.exec_command(cmd)
print(stdout.read().decode())

ssh.close()
