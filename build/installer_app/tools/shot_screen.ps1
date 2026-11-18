Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$screen = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$bitmap = New-Object System.Drawing.Bitmap $screen.Width, $screen.Height
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$graphics.CopyFromScreen($screen.Location, [System.Drawing.Point]::Empty, $screen.Size)
$dest = "C:\Users\Dell\.gemini\antigravity\brain\5bf1f793-a593-488a-8501-e22f375c5231\installer_fresh_screen.png"
$bitmap.Save($dest)
$graphics.Dispose()
$bitmap.Dispose()
Write-Output "Screenshot saved to $dest"

