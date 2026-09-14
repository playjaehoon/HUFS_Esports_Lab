param(
    [string]$FontPath = "$PSScriptRoot\..\static\fonts\Gladiora-Bold.ttf",
    [string]$OutputPath = "$PSScriptRoot\..\static\images\logo.png"
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing

$fontFile = (Resolve-Path -LiteralPath $FontPath).Path
$outputFile = [System.IO.Path]::GetFullPath($OutputPath)
$outputDirectory = [System.IO.Path]::GetDirectoryName($outputFile)
[System.IO.Directory]::CreateDirectory($outputDirectory) | Out-Null

$fonts = New-Object System.Drawing.Text.PrivateFontCollection
$path = New-Object System.Drawing.Drawing2D.GraphicsPath
$format = New-Object System.Drawing.StringFormat
$matrix = New-Object System.Drawing.Drawing2D.Matrix
$fonts.AddFontFile($fontFile)

$text = 'Philips Evnia Esports Lab'
$fontFamily = $fonts.Families[0]
$path.AddString($text, $fontFamily, [int][System.Drawing.FontStyle]::Regular, 180, [System.Drawing.PointF]::new(0, 0), $format)
$bounds = $path.GetBounds()
$padding = 24
$matrix.Translate($padding - $bounds.X, $padding - $bounds.Y)
$path.Transform($matrix)
$bounds = $path.GetBounds()

$width = [int][Math]::Ceiling($bounds.Right + $padding)
$height = [int][Math]::Ceiling($bounds.Bottom + $padding)
$bitmap = New-Object System.Drawing.Bitmap($width, $height, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$graphics.Clear([System.Drawing.Color]::Transparent)
$graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
$graphics.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality

$brush = New-Object System.Drawing.Drawing2D.LinearGradientBrush(
    [System.Drawing.PointF]::new($bounds.Left, 0),
    [System.Drawing.PointF]::new($bounds.Right, 0),
    [System.Drawing.ColorTranslator]::FromHtml('#6BC1B3'),
    [System.Drawing.ColorTranslator]::FromHtml('#896AAC')
)
$blend = New-Object System.Drawing.Drawing2D.ColorBlend
$blend.Colors = @(
    [System.Drawing.ColorTranslator]::FromHtml('#6BC1B3'),
    [System.Drawing.ColorTranslator]::FromHtml('#55ACD9'),
    [System.Drawing.ColorTranslator]::FromHtml('#896AAC')
)
$blend.Positions = [single[]]@(0, 0.52, 1)
$brush.InterpolationColors = $blend
$graphics.FillPath($brush, $path)
$bitmap.Save($outputFile, [System.Drawing.Imaging.ImageFormat]::Png)

$brush.Dispose()
$graphics.Dispose()
$bitmap.Dispose()
$matrix.Dispose()
$format.Dispose()
$path.Dispose()
$fonts.Dispose()

Write-Output "Created transparent logo: $outputFile"
