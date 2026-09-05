param([string]$Title, [int]$X, [int]$Y)
Add-Type @'
using System;
using System.Text;
using System.Runtime.InteropServices;
public class U {
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr l);
  [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
  [DllImport("user32.dll")] public static extern void mouse_event(uint f, uint x, uint y, uint d, IntPtr e);
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L,T,R,B; }
  public delegate bool EnumProc(IntPtr h, IntPtr l);
  public static IntPtr Find(string title) {
    IntPtr found = IntPtr.Zero;
    EnumWindows((h,l)=>{ var t=new StringBuilder(256); GetWindowText(h,t,256);
      if(IsWindowVisible(h) && t.ToString().Contains(title)){found=h;return false;} return true; }, IntPtr.Zero);
    return found;
  }
  public static void ClickAt(IntPtr h, int rx, int ry) {
    RECT r; GetWindowRect(h, out r);
    SetForegroundWindow(h);
    System.Threading.Thread.Sleep(300);
    SetCursorPos(r.L + rx, r.T + ry);
    System.Threading.Thread.Sleep(120);
    mouse_event(0x0002,0,0,0,IntPtr.Zero); mouse_event(0x0004,0,0,0,IntPtr.Zero);
  }
}
'@
$h = [U]::Find($Title)
if ($h -eq [IntPtr]::Zero) { Write-Output "not found"; exit 1 }
[U]::ClickAt($h, $X, $Y)
Write-Output "clicked $Title at $X,$Y"
