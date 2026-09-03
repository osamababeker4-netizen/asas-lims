$ErrorActionPreference = 'Stop'

$env:TWILIO_ACCOUNT_SID = [Environment]::GetEnvironmentVariable('TWILIO_ACCOUNT_SID', 'User')
$env:TWILIO_AUTH_TOKEN = [Environment]::GetEnvironmentVariable('TWILIO_AUTH_TOKEN', 'User')
$env:TWILIO_VERIFY_SERVICE_SID = [Environment]::GetEnvironmentVariable('TWILIO_VERIFY_SERVICE_SID', 'User')

$phone = Read-Host 'Admin phone in E.164 format, for example +9665XXXXXXXX'
if ($phone -notmatch '^\+\d{8,15}$') {
    throw 'Phone must contain + and digits only.'
}

$securePassword = Read-Host 'Admin password (12 characters minimum)' -AsSecureString
$pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword)
try {
    $env:LIMS_BOOTSTRAP_PHONE = $phone
    $env:LIMS_BOOTSTRAP_PASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    & python .\server.py
}
finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    Remove-Item Env:LIMS_BOOTSTRAP_PASSWORD -ErrorAction SilentlyContinue
}
