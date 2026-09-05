param([string]$Title, [string]$Out)
Add-Type -AssemblyName System.Windows.Forms,System.Drawing
Add-Type @'
using System;
using System.Text;
using System.Runtime.InteropServices;
public class U {
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr l);
  [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr hdc, uint flags);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L,T,R,B; }
  public delegate bool EnumProc(IntPtr h, IntPtr l);
  public static IntPtr Find(string title) {
    IntPtr found = IntPtr.Zero;
    EnumWindows((h,l)=>{
      var t = new StringBuilder(256); GetWindowText(h,t,256);
      if (IsWindowVisible(h) && t.ToString().Contains(title)) { found = h; return false; }
      return true; }, IntPtr.Zero);
    return found;
  }
}
'@
$h = [U]::Find($Title)
if ($h -eq [IntPtr]::Zero) { Write-Output "window not found: $Title"; exit 1 }
[void][U]::SetForegroundWindow($h)
Start-Sleep -Milliseconds 600
$rc = New-Object U+RECT
[void][U]::GetWindowRect($h, [ref]$rc)
$w = $rc.R - $rc.L; $ht = $rc.B - $rc.T
$bmp = New-Object System.Drawing.Bitmap($w, $ht)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$hdc = $g.GetHdc()
[void][U]::PrintWindow($h, $hdc, 2)  # PW_RENDERFULLCONTENT
$g.ReleaseHdc($hdc)
$bmp.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose(); $bmp.Dispose()
Write-Output "saved ${w}x${ht} -> $Out"
