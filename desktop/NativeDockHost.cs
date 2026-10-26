// Product integration: embeds the two installed application windows as real child
// windows. No input injection, screen copying, or application database access.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.IO.Pipes;
using System.Linq;
using System.Runtime.InteropServices;
using System.Security.AccessControl;
using System.Security.Cryptography;
using System.Security.Principal;
using System.Text;
using System.Threading;
using System.Web.Script.Serialization;
using System.Windows.Forms;

internal static class Native {
    internal delegate bool EnumProc(IntPtr hwnd, IntPtr data);
    [StructLayout(LayoutKind.Sequential)] internal struct RECT { public int Left, Top, Right, Bottom; }
    [StructLayout(LayoutKind.Sequential)] internal struct POINT { public int X,Y; }
    [DllImport("user32.dll")] internal static extern bool EnumWindows(EnumProc cb, IntPtr data);
    [DllImport("user32.dll")] internal static extern bool EnumChildWindows(IntPtr hwnd, EnumProc cb, IntPtr data);
    [DllImport("user32.dll")] internal static extern bool IsWindow(IntPtr hwnd);
    [DllImport("user32.dll")] internal static extern bool IsWindowVisible(IntPtr hwnd);
    [DllImport("user32.dll")] internal static extern bool IsIconic(IntPtr hwnd);
    [DllImport("user32.dll",SetLastError=true)] internal static extern IntPtr SetParent(IntPtr hwnd,IntPtr parent);
    [DllImport("user32.dll")] internal static extern IntPtr GetParent(IntPtr hwnd);
    [DllImport("user32.dll")] internal static extern bool ScreenToClient(IntPtr hwnd,ref POINT point);
    [DllImport("user32.dll")] internal static extern bool ClientToScreen(IntPtr hwnd,ref POINT point);
    [DllImport("user32.dll")] internal static extern bool GetClientRect(IntPtr hwnd,out RECT rect);
    [DllImport("user32.dll")] internal static extern IntPtr GetAncestor(IntPtr hwnd,uint flags);
    [DllImport("user32.dll")] internal static extern bool GetWindowRect(IntPtr hwnd, out RECT rect);
    [DllImport("user32.dll")] internal static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] internal static extern uint GetWindowThreadProcessId(IntPtr hwnd, out uint pid);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] internal static extern int GetWindowText(IntPtr hwnd, StringBuilder value, int size);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] internal static extern int GetClassName(IntPtr hwnd, StringBuilder value, int size);
    [DllImport("user32.dll", EntryPoint="GetWindowLongPtrW")] internal static extern IntPtr GetLong(IntPtr hwnd, int index);
    [DllImport("user32.dll", EntryPoint="SetWindowLongPtrW")] internal static extern IntPtr SetLong(IntPtr hwnd, int index, IntPtr value);
    [DllImport("user32.dll")] internal static extern bool ShowWindow(IntPtr hwnd, int action);
    [DllImport("user32.dll")] internal static extern bool SetWindowPos(IntPtr hwnd, IntPtr after, int x, int y, int w, int h, uint flags);
    [DllImport("user32.dll")] internal static extern bool SetForegroundWindow(IntPtr hwnd);
    [DllImport("user32.dll")] internal static extern bool PostMessage(IntPtr hwnd, uint message, IntPtr w, IntPtr l);
    [DllImport("user32.dll")] internal static extern int SetWindowRgn(IntPtr hwnd, IntPtr region, bool redraw);
    [DllImport("gdi32.dll")] internal static extern IntPtr CreateRectRgn(int x1,int y1,int x2,int y2);
    [DllImport("gdi32.dll")] internal static extern bool DeleteObject(IntPtr obj);
    [DllImport("user32.dll")] internal static extern uint GetDpiForWindow(IntPtr hwnd);
    [DllImport("user32.dll")] internal static extern bool SetProcessDpiAwarenessContext(IntPtr context);
    [DllImport("user32.dll")] internal static extern bool RegisterHotKey(IntPtr hwnd,int id,uint mods,uint key);
    [DllImport("user32.dll")] internal static extern bool UnregisterHotKey(IntPtr hwnd,int id);
    internal static Rectangle Bounds(IntPtr hwnd) { RECT r; GetWindowRect(hwnd,out r); return Rectangle.FromLTRB(r.Left,r.Top,r.Right,r.Bottom); }
    internal static Rectangle ClientBounds(IntPtr hwnd) { RECT r;GetClientRect(hwnd,out r);var p=new POINT();ClientToScreen(hwnd,ref p);return new Rectangle(p.X,p.Y,r.Right-r.Left,r.Bottom-r.Top); }
    internal static uint Pid(IntPtr hwnd) { uint id; GetWindowThreadProcessId(hwnd,out id); return id; }
    internal static string Title(IntPtr hwnd) { var s=new StringBuilder(1024); GetWindowText(hwnd,s,s.Capacity); return s.ToString(); }
}

internal sealed class ToolWindow {
    internal string Tool, Exe;
    internal IntPtr Handle;
    internal IntPtr Parent;
    internal int Pid;
    internal long Started, Style, ExStyle;
    internal Rectangle Original, Last;
    internal bool WasVisible, Modified, Docked, Shown;
    internal Dictionary<string,object> Snapshot() { return new Dictionary<string,object> {
        {"tool",Tool},{"hwnd",Handle.ToInt64().ToString()},{"pid",Pid},{"exe",Exe},
        {"started",Started},{"style",Style},{"exStyle",ExStyle},{"parent",Parent.ToInt64().ToString()},
        {"x",Original.X},{"y",Original.Y},{"width",Original.Width},{"height",Original.Height},
        {"wasVisible",WasVisible}
    }; }
}

internal sealed class DockHost : Form {
    readonly string root, pipeName, journal;
    readonly JavaScriptSerializer json = new JavaScriptSerializer();
    readonly Dictionary<string,ToolWindow> tools = new Dictionary<string,ToolWindow>();
    readonly System.Windows.Forms.Timer timer = new System.Windows.Forms.Timer();
    readonly Dictionary<string,string> programs = new Dictionary<string,string>();
    readonly List<PendingOpen> pending = new List<PendingOpen>();
    StreamWriter bridge;
    IntPtr bridgeHandle, lastForeground;
    int bridgePid;
    Rectangle viewport;
    bool bridgeVisible, hotkeys, quitting;
    string active;
    NotifyIcon orxTray;
    Form standalone;
    Rectangle normalStandalone;
    bool standaloneFullscreen, standaloneMode;
    sealed class PendingOpen { internal string Tool; internal DateTime Until; internal StreamWriter Writer; internal object Id; }

    internal DockHost(string directory, string pipe) {
        root=directory; pipeName=pipe; journal=Path.Combine(root,"data",pipe.EndsWith(".test")?"native-window-test-state.json":"native-window-state.json");
        ShowInTaskbar=false; FormBorderStyle=FormBorderStyle.None; Size=new Size(1,1);
        var handle=Handle;
        programs["zotero"]=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles),"Zotero","zotero.exe");
        programs["openresearch"]=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"Programs","OpenResearch","OpenResearch.exe");
        Recover();
        timer.Interval=100; timer.Tick+=(s,e)=>TickWindows(); timer.Start();
        var server=new Thread(Serve); server.IsBackground=true; server.Start();
        File.WriteAllText(Path.Combine(root,"data",pipe.EndsWith(".test")?"native-host-test-runtime.json":"native-host-runtime.json"),json.Serialize(new { pid=Process.GetCurrentProcess().Id, pipe=pipeName }),Encoding.UTF8);
    }
    protected override void SetVisibleCore(bool value) { base.SetVisibleCore(false); }
    internal static string PipeName(string root) {
        using(var hash=SHA256.Create()) return "ResearchBridge.NativeDock."+BitConverter.ToString(hash.ComputeHash(Encoding.UTF8.GetBytes(root.ToLowerInvariant()))).Replace("-","").Substring(0,16).ToLowerInvariant();
    }
    // Read-only product maintenance check. A missing pipe is never proof of detach.
    internal static object VerifyDetached() {
        var expected=new Dictionary<string,string> {
            {"zotero",Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles),"Zotero","zotero.exe")},
            {"openresearch",Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"Programs","OpenResearch","orx.exe")}
        };
        var pids=new Dictionary<int,string>();
        foreach(var tool in expected.Keys) {
            string process=tool=="zotero"?"zotero":"orx";
            foreach(var p in Process.GetProcessesByName(process))if(SameExe(p.Id,expected[tool]))pids[p.Id]=tool;
        }
        var found=new Dictionary<long,Dictionary<string,object>>();
        Native.EnumProc inspect=(h,p)=> {
            int pid=(int)Native.Pid(h);if(!pids.ContainsKey(pid))return true;
            string tool=pids[pid];var cls=new StringBuilder(256);Native.GetClassName(h,cls,cls.Capacity);
            bool main=tool=="zotero"?cls.ToString()=="MozillaWindowClass"&&Native.Title(h).EndsWith("Zotero"):
                Native.Title(h).EndsWith("OpenResearch");
            if(main) {
                long parent=Native.GetParent(h).ToInt64();bool child=(Native.GetLong(h,-16).ToInt64()&0x40000000L)!=0;
                found[h.ToInt64()]=new Dictionary<string,object>{{"tool",tool},{"pid",pid},{"hwnd",h.ToInt64().ToString()},{"parent",parent.ToString()},{"child",child},{"detached",parent==0&&!child}};
            }
            return true;
        };
        Native.EnumWindows((h,p)=> {inspect(h,p);Native.EnumChildWindows(h,inspect,IntPtr.Zero);return true;},IntPtr.Zero);
        bool all=expected.Keys.All(tool=>found.Values.Any(w=>Convert.ToString(w["tool"])==tool))&&found.Values.All(w=>Convert.ToBoolean(w["detached"]));
        return new {safeToRestart=all,readOnly=true,checkedAtUtc=DateTime.UtcNow.ToString("o"),windows=found.Values.ToArray()};
    }
    internal static int Number(Dictionary<string,object> d,string key,int fallback=0) { object v; return d.TryGetValue(key,out v)?Convert.ToInt32(v):fallback; }
    static string ReadText(Dictionary<string,object> d,string key) { object v; return d.TryGetValue(key,out v)?Convert.ToString(v):""; }
    static bool Flag(Dictionary<string,object> d,string key) { object v; return d.TryGetValue(key,out v)&&Convert.ToBoolean(v); }
    static void Send(StreamWriter writer,object data) {
        if(writer==null)return;
        try { lock(writer) { writer.WriteLine(new JavaScriptSerializer().Serialize(data)); writer.Flush(); } } catch {}
    }
    void Event(string type,string tool) { Send(bridge,new { @event=type,tool=tool }); }
    void Serve() {
        while(!quitting) {
            try {
                var acl=new PipeSecurity();
                acl.SetAccessRuleProtection(true,false);
                acl.AddAccessRule(new PipeAccessRule(WindowsIdentity.GetCurrent().User,PipeAccessRights.FullControl,AccessControlType.Allow));
                var pipe=new NamedPipeServerStream(pipeName,PipeDirection.InOut,4,PipeTransmissionMode.Byte,PipeOptions.Asynchronous,4096,4096,acl);
                pipe.WaitForConnection();
                var thread=new Thread(()=>ReadClient(pipe)); thread.IsBackground=true; thread.Start();
            } catch { Thread.Sleep(300); }
        }
    }
    void ReadClient(NamedPipeServerStream pipe) {
        StreamWriter writer=null;
        try {
            writer=new StreamWriter(pipe,new UTF8Encoding(false),4096,true); writer.AutoFlush=true;
            using(var reader=new StreamReader(pipe,Encoding.UTF8,false,4096,true)) {
                string line;
                while((line=reader.ReadLine())!=null) {
                    if(line.Length>16384)break;
                    var d=new JavaScriptSerializer().Deserialize<Dictionary<string,object>>(line);
                    var output=writer;
                    BeginInvoke((Action)(()=>HandleCommand(d,output)));
                }
            }
        } catch {} finally {
            var output=writer;
            try { BeginInvoke((Action)(()=> { if(bridge==output) DetachBridge(); })); } catch {}
            pipe.Dispose();
        }
    }
    void Reply(StreamWriter writer,object id,object value) { Send(writer,new { id=id,result=value }); }
    void HandleCommand(Dictionary<string,object> d,StreamWriter writer) {
        object id=d.ContainsKey("id")?d["id"]:null;
        try {
            string command=ReadText(d,"command");
            if(command=="attach") {
                var hwnd=new IntPtr(long.Parse(ReadText(d,"hwnd"))); int pid=Number(d,"pid");
                string expected=Path.Combine(root,"node_modules","electron","dist","electron.exe");
                if(!Native.IsWindow(hwnd)||Native.Pid(hwnd)!=pid||!SameExe(pid,expected))throw new Exception("无法确认 Research Nexus 窗口身份。");
                if(bridge!=null&&bridge!=writer)DetachBridge();
                bridge=writer;bridgeHandle=hwnd;bridgePid=pid;
                Reply(writer,id,new { ok=true });return;
            }
            if(command=="open") {
                string tool=ReadText(d,"tool"); if(!programs.ContainsKey(tool))throw new Exception("不支持的本地工具。");
                RefreshPrograms();
                if(!File.Exists(programs[tool]))throw new Exception("未找到本地 "+tool+" 应用。");
                var found=Find(tool);
                if(found==null) {
                    // Multiple clicks while the app starts share one launch.
                    if(!pending.Any(p=>p.Tool==tool))Process.Start(new ProcessStartInfo(programs[tool]) { UseShellExecute=false,CreateNoWindow=true,WorkingDirectory=Path.GetDirectoryName(programs[tool]) });
                    pending.Add(new PendingOpen { Tool=tool,Until=DateTime.Now.AddSeconds(25),Writer=writer,Id=id });
                } else { Open(found); Reply(writer,id,new { ok=true,tool=tool,pid=found.Pid,hwnd=found.Handle.ToInt64().ToString(),native=true }); }
                return;
            }
            if(command=="status") { Reply(writer,id,new { native=true,mode="child-window",fit="complete-client-area",active=active,bridge=bridgeHandle.ToInt64().ToString(),standalone=standaloneMode,viewport=RectData(viewport),windows=tools.Values.Select(x=>new {tool=x.Tool,pid=x.Pid,hwnd=x.Handle.ToInt64().ToString(),parent=Native.GetParent(x.Handle).ToInt64().ToString(),child=(Native.GetLong(x.Handle,-16).ToInt64()&0x40000000L)!=0,visible=Native.IsWindowVisible(x.Handle),docked=x.Docked,exe=x.Exe,bounds=RectData(Native.Bounds(x.Handle)),client=RectData(Native.ClientBounds(x.Handle))}).ToArray() });return; }
            if(command=="shutdown-host") {
                // Component maintenance restores original app windows; never kills them.
                foreach(var t in tools.Values.ToList())Restore(t,t.WasVisible);
                tools.Clear();SaveJournal();quitting=true;SetHotkeys(false);
                if(orxTray!=null)orxTray.Dispose();if(standalone!=null)standalone.Hide();
                Reply(writer,id,new {ok=true});BeginInvoke((Action)(()=>Application.Exit()));return;
            }
            if(bridge!=writer)throw new Exception("本地窗口连接尚未建立。");
            if(command=="layout") {
                var b=(Dictionary<string,object>)d["bounds"];
                viewport=new Rectangle(Number(b,"x"),Number(b,"y"),Number(b,"width"),Number(b,"height"));
                bridgeVisible=Flag(d,"visible");active=ReadText(d,"tool");
                LayoutTools(false);if(id!=null)Reply(writer,id,new {ok=true});return;
            }
            if(command=="release") {
                string tool=ReadText(d,"tool"); ToolWindow target;
                if(tools.TryGetValue(tool,out target)) {
                    if(tool=="openresearch")ShowStandalone();
                    else { Restore(target,true);tools.Remove(tool);SaveJournal(); }
                    if(active==tool)active="";
                }
                Event("released",tool);Reply(writer,id,new {ok=true});return;
            }
            if(command=="detach") { DetachBridge();Reply(writer,id,new {ok=true});return; }
            throw new Exception("未知本地窗口操作。");
        } catch(Exception e) { Send(writer,new {id=id,error=e.Message}); }
    }
    static bool SameExe(int pid,string exe) { try { return String.Equals(Process.GetProcessById(pid).MainModule.FileName,exe,StringComparison.OrdinalIgnoreCase); } catch { return false; } }
    void RefreshPrograms() {
        try {
            var file=Path.Combine(root,"data","config.json");
            if(!File.Exists(file))return;
            var settings=json.DeserializeObject(File.ReadAllText(file,Encoding.UTF8)) as Dictionary<string,object>;
            foreach(var tool in new [] {"zotero","openresearch"}) {
                object value;
                if(settings!=null&&settings.TryGetValue(tool+"_exe",out value)) {
                    string exe=Convert.ToString(value);
                    if(Path.IsPathRooted(exe)&&String.Equals(Path.GetExtension(exe),".exe",StringComparison.OrdinalIgnoreCase)&&File.Exists(exe))programs[tool]=exe;
                }
            }
        } catch { }
    }
    static object RectData(Rectangle r) {return new {x=r.X,y=r.Y,width=r.Width,height=r.Height};}
    ToolWindow Find(string tool) {
        RefreshPrograms();
        ToolWindow existing;
        if(tools.TryGetValue(tool,out existing)&&Native.IsWindow(existing.Handle)&&Native.Pid(existing.Handle)==existing.Pid)return existing;
        string sibling=Path.Combine(Path.GetDirectoryName(programs[tool]),"orx.exe");
        string exe=tool=="zotero"||!File.Exists(sibling)?programs[tool]:sibling;
        var matches=new List<IntPtr>();
        Native.EnumWindows((h,p)=> {
            if(!SameExe((int)Native.Pid(h),exe))return true;
            string title=Native.Title(h); var cls=new StringBuilder(256);Native.GetClassName(h,cls,cls.Capacity);
            if(tool=="zotero" ? title.EndsWith("Zotero")&&cls.ToString()=="MozillaWindowClass" : title.EndsWith("OpenResearch"))matches.Add(h);
            return true;
        },IntPtr.Zero);
        if(matches.Count==0)return null;
        var hwnd=matches.OrderByDescending(h=> {var r=Native.Bounds(h);return (long)r.Width*r.Height;}).First();
        var proc=Process.GetProcessById((int)Native.Pid(hwnd));
        return new ToolWindow { Tool=tool,Handle=hwnd,Pid=proc.Id,Started=proc.StartTime.ToUniversalTime().Ticks,Exe=exe,
            Style=Native.GetLong(hwnd,-16).ToInt64(),ExStyle=Native.GetLong(hwnd,-20).ToInt64(),Parent=Native.GetParent(hwnd),Original=Native.Bounds(hwnd),WasVisible=Native.IsWindowVisible(hwnd) };
    }
    void Open(ToolWindow tool) {
        if(standaloneMode) { standaloneMode=false;if(standalone!=null)standalone.Hide(); }
        tools[tool.Tool]=tool;active=tool.Tool;tool.Docked=true;
        if(tool.Tool=="openresearch")CreateOrxTray();
        SaveJournal();
        if(bridge!=null&&Native.IsWindow(bridgeHandle)) {
            bridgeVisible=true;Event("activate",tool.Tool);LayoutTools(true);
        } else if(tool.Tool=="openresearch")ShowStandalone();
        else { Restore(tool,true);tools.Remove(tool.Tool);SaveJournal(); }
    }
    void Modify(ToolWindow state,IntPtr parent) {
        if(state.Modified&&Native.GetParent(state.Handle)==parent)return;
        if(Native.IsIconic(state.Handle))Native.ShowWindow(state.Handle,9);
        Native.ShowWindow(state.Handle,0);
        long style=(state.Style & ~0xB1CF0000L)|0x46000000L; // child; no popup/caption/frame/minimized/maximized state
        long ex=state.ExStyle & ~0x00060301L; // no app taskbar entry or non-client edge styles
        Native.SetLong(state.Handle,-16,new IntPtr(style));Native.SetLong(state.Handle,-20,new IntPtr(ex));
        Native.SetParent(state.Handle,parent);
        if(Native.GetParent(state.Handle)!=parent) {Restore(state,true);throw new Exception("无法将本地窗口嵌入工作台，请使用独立窗口。");}
        Native.SetWindowPos(state.Handle,IntPtr.Zero,0,0,0,0,0x0037);state.Modified=true;
        state.Last=Rectangle.Empty;state.Shown=false;
    }
    void Place(ToolWindow state,Rectangle rect,bool raise,IntPtr parent) {
        if(rect.Width<1||rect.Height<1)return;
        Modify(state,parent);
        // Fit the actual client area, not a guessed titlebar crop. Some custom
        // windows keep an invisible 8px resize frame even without a caption.
        for(int attempt=0;attempt<2;attempt++) {
            var window=Native.Bounds(state.Handle);var client=Native.ClientBounds(state.Handle);
            int left=client.Left-window.Left,top=client.Top-window.Top;
            int right=window.Right-client.Right,bottom=window.Bottom-client.Bottom;
            var point=new Native.POINT {X=rect.X-left,Y=rect.Y-top};Native.ScreenToClient(parent,ref point);
            var outer=new Rectangle(point.X,point.Y,rect.Width+left+right,rect.Height+top+bottom);
            if(outer==state.Last&&client==rect)break;
            Native.SetWindowPos(state.Handle,IntPtr.Zero,outer.X,outer.Y,outer.Width,outer.Height,0x0010);
            var rgn=Native.CreateRectRgn(left,top,left+rect.Width,top+rect.Height);
            if(Native.SetWindowRgn(state.Handle,rgn,true)==0)Native.DeleteObject(rgn);
            state.Last=outer;
        }
        if(!state.Shown||!Native.IsWindowVisible(state.Handle))Native.ShowWindow(state.Handle,4);
        if(raise)Native.SetWindowPos(state.Handle,IntPtr.Zero,0,0,0,0,0x0013);
        state.Shown=true;
    }
    void Hide(ToolWindow state) { if(state.Shown&&Native.IsWindow(state.Handle))Native.ShowWindow(state.Handle,0);state.Shown=false; }
    void LayoutTools(bool raise) {
        foreach(var state in tools.Values) {
            if(!Native.IsWindow(state.Handle))continue;
            if(standaloneMode&&state.Tool=="openresearch") {
                if(standalone!=null&&standalone.Visible&&standalone.WindowState!=FormWindowState.Minimized) {
                    var point=standalone.PointToScreen(Point.Empty);Place(state,new Rectangle(point,standalone.ClientSize),raise,standalone.Handle);
                } else Hide(state);
            } else if(state.Docked&&bridgeVisible&&state.Tool==active&&Native.IsWindow(bridgeHandle))Place(state,viewport,raise,bridgeHandle);
            else Hide(state);
        }
    }
    void Restore(ToolWindow state,bool visible) {
        if(!Native.IsWindow(state.Handle)||Native.Pid(state.Handle)!=state.Pid)return;
        Native.ShowWindow(state.Handle,0);
        Native.SetWindowRgn(state.Handle,IntPtr.Zero,true);
        Native.SetParent(state.Handle,state.Parent);
        Native.SetLong(state.Handle,-16,new IntPtr(state.Style));Native.SetLong(state.Handle,-20,new IntPtr(state.ExStyle));
        var r=state.Original;
        Native.SetWindowPos(state.Handle,IntPtr.Zero,r.X,r.Y,Math.Max(100,r.Width),Math.Max(100,r.Height),0x0034);
        Native.ShowWindow(state.Handle,visible?4:0);state.Modified=false;state.Shown=visible;state.Docked=false;state.Last=Rectangle.Empty;
    }
    void DetachBridge() {
        bridge=null;bridgeHandle=IntPtr.Zero;bridgePid=0;bridgeVisible=false;active="";
        foreach(var t in tools.Values.ToList()) {
            if(t.Tool=="openresearch") { Restore(t,false); }
            else { Restore(t,false);tools.Remove(t.Tool); }
        }
        standaloneMode=false;if(standalone!=null)standalone.Hide();SaveJournal();SetHotkeys(false);
    }
    void CreateOrxTray() {
        if(orxTray!=null)return;
        var menu=new ContextMenuStrip();
        menu.Items.Add("打开 OpenResearch",null,(s,e)=> {
            if(bridge!=null&&Native.IsWindow(bridgeHandle)) { active="openresearch";bridgeVisible=true;standaloneMode=false;ToolWindow t;if(tools.TryGetValue("openresearch",out t))t.Docked=true;if(standalone!=null)standalone.Hide();Event("activate","openresearch");LayoutTools(true); }
            else ShowStandalone();
        });
        menu.Items.Add("独立窗口",null,(s,e)=> { ShowStandalone();Event("released","openresearch"); });
        menu.Items.Add(new ToolStripSeparator());
        menu.Items.Add("退出 OpenResearch",null,(s,e)=> {
            ToolWindow t;if(tools.TryGetValue("openresearch",out t)) { Restore(t,true);Native.PostMessage(t.Handle,0x0010,IntPtr.Zero,IntPtr.Zero);tools.Remove("openresearch"); }
            if(standalone!=null)standalone.Hide();standaloneMode=false;
            orxTray.Visible=false;orxTray.Dispose();orxTray=null;SaveJournal();Event("closed","openresearch");
        });
        orxTray=new NotifyIcon { Icon=new Icon(Path.Combine(root,"desktop","nexus-aurora-soft-rainbow.ico")),Text="OpenResearch · 本地应用",ContextMenuStrip=menu,Visible=true };
        orxTray.MouseClick+=(s,e)=> { if(e.Button==MouseButtons.Left)menu.Items[0].PerformClick(); };
    }
    void ShowStandalone() {
        ToolWindow t;if(!tools.TryGetValue("openresearch",out t)||!Native.IsWindow(t.Handle))return;
        if(standalone==null) {
            standalone=new Form { Text="OpenResearch · 本地应用",Size=new Size(1360,900),MinimumSize=new Size(900,600),StartPosition=FormStartPosition.CenterScreen,Icon=new Icon(Path.Combine(root,"desktop","nexus-aurora-soft-rainbow.ico")) };
            standalone.FormClosing+=(s,e)=> { if(!quitting) { e.Cancel=true;standalone.Hide();ToolWindow current;if(tools.TryGetValue("openresearch",out current))Hide(current); } };
            standalone.Move+=(s,e)=>LayoutTools(false);standalone.Resize+=(s,e)=>LayoutTools(false);
            standalone.Activated+=(s,e)=>LayoutTools(true);
        }
        standaloneMode=true;t.Docked=false;standalone.Show();standalone.Activate();LayoutTools(true);
    }
    void TickWindows() {
        foreach(var p in pending.ToList()) {
            var tool=Find(p.Tool);
            if(tool!=null) { pending.Remove(p);Open(tool);Reply(p.Writer,p.Id,new {ok=true,tool=p.Tool,pid=tool.Pid,hwnd=tool.Handle.ToInt64().ToString(),native=true}); }
            else if(DateTime.Now>p.Until) { pending.Remove(p);Send(p.Writer,new {id=p.Id,error="本地应用窗口尚未就绪，请重试。"}); }
        }
        if(bridge!=null&&(!Native.IsWindow(bridgeHandle)||!SameExe(bridgePid,Path.Combine(root,"node_modules","electron","dist","electron.exe"))))DetachBridge();
        foreach(var t in tools.Values.ToList()) if(!Native.IsWindow(t.Handle)||Native.Pid(t.Handle)!=t.Pid) {
            tools.Remove(t.Tool);Event("closed",t.Tool);SaveJournal();
            if(t.Tool=="openresearch"&&orxTray!=null) {orxTray.Dispose();orxTray=null;if(standalone!=null)standalone.Hide();}
        }
        foreach(var t in tools.Values) if(t.Shown&&bridgeVisible&&!Native.IsWindowVisible(t.Handle)&&Native.IsWindowVisible(bridgeHandle)) {
            t.Shown=false;
            if(standaloneMode&&standalone!=null)standalone.Hide();
            else if(bridgeVisible&&active==t.Tool) {bridgeVisible=false;Event("hide",t.Tool);}
        }
        IntPtr foreground=Native.GetForegroundWindow();
        bool related=foreground==bridgeHandle&&bridgeHandle!=IntPtr.Zero;
        if(standalone!=null&&foreground==standalone.Handle&&standaloneMode)related=true;
        foreach(var t in tools.Values) if(Native.Pid(foreground)==t.Pid) {
            related=true;
        }
        if(foreground!=lastForeground) { if(related)LayoutTools(true);lastForeground=foreground; }
        LayoutTools(related);
        SetHotkeys(related&&((bridge!=null&&bridgeVisible&&tools.ContainsKey(active??""))||standaloneMode));
    }
    void SetHotkeys(bool wanted) {
        if(wanted==hotkeys)return;
        if(wanted) { Native.RegisterHotKey(Handle,11,0x4000,0x7A);Native.RegisterHotKey(Handle,12,0x4001,0x73); }
        else { Native.UnregisterHotKey(Handle,11);Native.UnregisterHotKey(Handle,12); }
        hotkeys=wanted;
    }
    protected override void WndProc(ref Message m) {
        if(m.Msg==0x0312) {
            if(m.WParam.ToInt32()==11) {
                if(standaloneMode&&standalone!=null) {
                    if(!standaloneFullscreen) {normalStandalone=standalone.Bounds;standalone.FormBorderStyle=FormBorderStyle.None;standalone.Bounds=Screen.FromControl(standalone).Bounds;}
                    else {standalone.FormBorderStyle=FormBorderStyle.Sizable;standalone.Bounds=normalStandalone;}
                    standaloneFullscreen=!standaloneFullscreen;LayoutTools(true);
                } else Event("fullscreen",active);
            } else if(m.WParam.ToInt32()==12) {
                if(standaloneMode&&standalone!=null)standalone.Close();else Event("hide",active);
            }
            return;
        }
        base.WndProc(ref m);
    }
    void SaveJournal() { try { File.WriteAllText(journal,json.Serialize(tools.Values.Select(x=>x.Snapshot()).ToArray()),Encoding.UTF8); } catch {} }
    void Recover() {
        if(!File.Exists(journal))return;
        try {
            var saved=json.Deserialize<List<Dictionary<string,object>>>(File.ReadAllText(journal,Encoding.UTF8));
            foreach(var d in saved) {
                var hwnd=new IntPtr(long.Parse(ReadText(d,"hwnd")));int pid=Number(d,"pid");
                if(!Native.IsWindow(hwnd)||Native.Pid(hwnd)!=pid||!SameExe(pid,ReadText(d,"exe")))continue;
                if(Process.GetProcessById(pid).StartTime.ToUniversalTime().Ticks!=Convert.ToInt64(d["started"]))continue;
                var t=new ToolWindow { Tool=ReadText(d,"tool"),Handle=hwnd,Pid=pid,Exe=ReadText(d,"exe"),Parent=new IntPtr(d.ContainsKey("parent")?long.Parse(ReadText(d,"parent")):0),Style=Convert.ToInt64(d["style"]),ExStyle=Convert.ToInt64(d["exStyle"]),Original=new Rectangle(Number(d,"x"),Number(d,"y"),Number(d,"width"),Number(d,"height")) };
                Restore(t,true);
            }
            File.Delete(journal);
        } catch {}
    }
    internal void SelfTest() {
        var parent=new Form {Text="RB embedding fixture",Bounds=new Rectangle(20,20,1400,1000)};parent.Show();
        var fixture=new Form {Text="Native docking fixture",Bounds=new Rectangle(100,100,700,500)};fixture.Show();
        var t=new ToolWindow {Tool="zotero",Handle=fixture.Handle,Parent=Native.GetParent(fixture.Handle),Pid=Process.GetCurrentProcess().Id,Style=Native.GetLong(fixture.Handle,-16).ToInt64(),ExStyle=Native.GetLong(fixture.Handle,-20).ToInt64(),Original=Native.Bounds(fixture.Handle)};
        var target=new Rectangle(324,180,850,650);Place(t,target,true,parent.Handle);
        bool docked=Native.ClientBounds(t.Handle)==target&&Native.GetParent(t.Handle)==parent.Handle;
        Hide(t);bool hidden=!Native.IsWindowVisible(t.Handle);
        Place(t,new Rectangle(30,60,1280,900),true,parent.Handle);bool full=Native.ClientBounds(t.Handle)==new Rectangle(30,60,1280,900);
        Restore(t,true);bool restored=Native.Bounds(t.Handle)==t.Original&&Native.GetLong(t.Handle,-16).ToInt64()==t.Style&&Native.GetParent(t.Handle)==t.Parent;
        t.Tool="openresearch";tools[t.Tool]=t;bridgeHandle=parent.Handle;Place(t,target,true,parent.Handle);DetachBridge();
        bool detached=Native.GetParent(t.Handle)==t.Parent&&!Native.IsWindowVisible(t.Handle);
        parent.Dispose();bool survives=Native.IsWindow(t.Handle);
        File.WriteAllText(Path.Combine(root,"data","native-dock-smoke.json"),json.Serialize(new {passed=docked&&hidden&&full&&restored&&detached&&survives,actual_native_window=true,child_parent_verified=docked,complete_client_area=docked,hide_preserves_window=hidden,fullscreen_layout=full,original_window_restored=restored,detach_restores_parent=detached,survives_parent_close=survives,no_fixed_content_crop=true}),Encoding.UTF8);
        fixture.Dispose();quitting=true;Application.Exit();
    }
}

internal static class Program {
    [STAThread] static void Main(string[] args) {
        string root=Path.GetFullPath(Path.Combine(AppDomain.CurrentDomain.BaseDirectory,".."));
        Directory.CreateDirectory(Path.Combine(root,"data"));
        if(args.Contains("--verify-detached")) {
            File.WriteAllText(Path.Combine(root,"data","native-detach-verification.json"),new JavaScriptSerializer().Serialize(DockHost.VerifyDetached()),Encoding.UTF8);
            return;
        }
        try { Native.SetProcessDpiAwarenessContext(new IntPtr(-4)); } catch {}
        string pipe=DockHost.PipeName(root);
        bool test=args.Contains("--self-test");if(test)pipe+=".test";
        bool owned;
        using(var mutex=new Mutex(true,"Local\\"+pipe+"."+WindowsIdentity.GetCurrent().User.Value,out owned)) {
            if(!owned) {
                if(args.Contains("--open-openresearch")) {
                    try { using(var client=new NamedPipeClientStream(".",pipe,PipeDirection.InOut)) {client.Connect(3000);var w=new StreamWriter(client,new UTF8Encoding(false));w.WriteLine("{\"id\":1,\"command\":\"open\",\"tool\":\"openresearch\"}");w.Flush();new StreamReader(client).ReadLine();} } catch {}
                }
                return;
            }
            Application.EnableVisualStyles();Application.SetCompatibleTextRenderingDefault(false);
            var host=new DockHost(root,pipe);
            if(test)host.BeginInvoke((Action)(()=>host.SelfTest()));
            else if(args.Contains("--open-openresearch"))new Thread(()=> {Thread.Sleep(500);try {using(var c=new NamedPipeClientStream(".",pipe,PipeDirection.InOut)){c.Connect(3000);var w=new StreamWriter(c,new UTF8Encoding(false));w.WriteLine("{\"id\":1,\"command\":\"open\",\"tool\":\"openresearch\"}");w.Flush();new StreamReader(c).ReadLine();}}catch{}}) {IsBackground=true}.Start();
            Application.Run(host);
        }
    }
}
