// SPDX-License-Identifier: GPL-2.0-or-later
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.RegularExpressions;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;
using System.Reflection;

[assembly: AssemblyTitle("音楽ライブラリ")]
[assembly: AssemblyProduct("Music Library")]
[assembly: AssemblyDescription("音源フォルダーを検索・再生するデスクトップアプリ")]
[assembly: AssemblyVersion("0.2.1.0")]
[assembly: AssemblyFileVersion("0.2.1.0")]

static class Program
{
    [DllImport("user32.dll")] static extern bool SetProcessDPIAware();
    [DllImport("shell32.dll", CharSet = CharSet.Unicode)] static extern int SetCurrentProcessExplicitAppUserModelID(string id);
    public static readonly string Bundle = AppDomain.CurrentDomain.BaseDirectory;
    public static string DataHome = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "MusicLibraryBrowser");
    public static string Python { get { return Path.Combine(Bundle, "runtime", "python.exe"); } }
    public static string Script { get { return Path.Combine(Bundle, "app", "library_app.py"); } }
    public static Icon AppIcon = LoadIcon();
    static Icon LoadIcon()
    {
        using (Stream stream = Assembly.GetExecutingAssembly().GetManifestResourceStream("MusicLibrary.Icon"))
        using (Icon icon = new Icon(stream)) return (Icon)icon.Clone();
    }

    public static string Quote(string value)
    {
        StringBuilder result = new StringBuilder("\""); int slashes = 0;
        foreach (char c in value)
        {
            if (c == '\\') { slashes++; continue; }
            if (c == '"') { result.Append('\\', slashes * 2 + 1); result.Append(c); }
            else { result.Append('\\', slashes); result.Append(c); }
            slashes = 0;
        }
        result.Append('\\', slashes * 2); result.Append('"'); return result.ToString();
    }
    public static ProcessStartInfo StartInfo(string[] args)
    {
        List<string> values = new List<string>();
        values.Add(Quote(Script));
        foreach (string arg in args) values.Add(Quote(arg));
        ProcessStartInfo info = new ProcessStartInfo(Python, string.Join(" ", values.ToArray()));
        info.UseShellExecute = false; info.CreateNoWindow = true;
        info.WorkingDirectory = Bundle;
        info.RedirectStandardOutput = true; info.RedirectStandardError = true;
        info.StandardOutputEncoding = Encoding.UTF8; info.StandardErrorEncoding = Encoding.UTF8;
        info.EnvironmentVariables["PYTHONUTF8"] = "1";
        info.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8";
        info.EnvironmentVariables["PYTHONDONTWRITEBYTECODE"] = "1";
        info.EnvironmentVariables.Remove("PYTHONHOME"); info.EnvironmentVariables.Remove("PYTHONPATH");
        return info;
    }
    [STAThread] static int Main(string[] args)
    {
        if (args.Length > 0 && args[0] == "--headless")
        {
            List<string> forwarded = new List<string>(args); forwarded.RemoveAt(0);
            using (Process process = new Process())
            {
                process.StartInfo = StartInfo(forwarded.ToArray());
                process.OutputDataReceived += delegate(object sender, DataReceivedEventArgs e) { if (e.Data != null) Console.WriteLine(e.Data); };
                process.ErrorDataReceived += delegate(object sender, DataReceivedEventArgs e) { if (e.Data != null) Console.Error.WriteLine(e.Data); };
                process.Start(); process.BeginOutputReadLine(); process.BeginErrorReadLine(); process.WaitForExit(); return process.ExitCode;
            }
        }
        try { SetProcessDPIAware(); } catch { }
        try { SetCurrentProcessExplicitAppUserModelID("MusicLibrary.Desktop"); } catch { }
        Application.EnableVisualStyles(); Application.SetCompatibleTextRenderingDefault(false);
        if (args.Length == 2 && args[0] == "--self-test")
        {
            if (Quote(@"C:\Music Files\") != "\"C:\\Music Files\\\\\"") return 2;
            using (MainForm form = new MainForm(null))
            {
                form.PrepareSnapshot();
                using (Bitmap bitmap = new Bitmap(form.Width, form.Height))
                { form.DrawToBitmap(bitmap, new Rectangle(Point.Empty, form.Size)); bitmap.Save(args[1]); }
            }
            return File.Exists(args[1]) ? 0 : 1;
        }
        string initial = null;
        for (int i = 0; i < args.Length; i++)
        {
            if (args[i] == "--data-home" && i + 1 < args.Length) DataHome = Path.GetFullPath(args[++i]);
            else if (Directory.Exists(args[i])) initial = args[i];
        }
        using (System.Threading.Mutex marker = new System.Threading.Mutex(false, "MusicLibraryDesktop"))
            Application.Run(new MainForm(initial));
        return 0;
    }
}

sealed class MainForm : Form
{
    TextBox source = new TextBox(); Label status = new Label(); ProgressBar progress = new ProgressBar();
    Button start = new Button(), browse = new Button(), stop = new Button(), openBrowser = new Button();
    CheckBox refresh = new CheckBox(); Process worker; string url; bool existingServer;
    bool snapshotMode; LibraryForm libraryWindow; bool closing;
    protected override bool ShowWithoutActivation { get { return snapshotMode; } }
    public void PrepareSnapshot()
    {
        snapshotMode = true; ShowInTaskbar = false; Opacity = 0; Show(); Application.DoEvents();
    }
    public MainForm(string initial)
    {
        Text = "音楽ライブラリ"; Icon = Program.AppIcon; ClientSize = new Size(720, 370); MinimumSize = new Size(650, 420);
        StartPosition = FormStartPosition.CenterScreen; Font = new Font("Yu Gothic UI", 10F);
        BackColor = Color.FromArgb(245, 247, 250); AutoScaleMode = AutoScaleMode.Dpi;
        Label title = new Label { Text = "音楽ライブラリ", Font = new Font(Font.FontFamily, 22F, FontStyle.Bold), AutoSize = true, Location = new Point(24, 18) };
        Label hint = new Label { Text = "音源フォルダーを選ぶと、このアプリで楽曲を検索・再生できます。", AutoSize = true, Location = new Point(27, 72) };
        Label caption = new Label { Text = "音源フォルダー", AutoSize = true, Location = new Point(27, 111) };
        source.SetBounds(28, 138, 532, 30); source.Anchor = AnchorStyles.Top | AnchorStyles.Left | AnchorStyles.Right;
        browse.Text = "選択…"; browse.SetBounds(572, 135, 118, 34); browse.Anchor = AnchorStyles.Top | AnchorStyles.Right;
        browse.Click += delegate { using (FolderBrowserDialog dialog = new FolderBrowserDialog()) { dialog.Description = "音源が入っているフォルダーを選択してください"; dialog.ShowNewFolderButton = false; if (Directory.Exists(source.Text)) dialog.SelectedPath = source.Text; if (dialog.ShowDialog(this) == DialogResult.OK) source.Text = dialog.SelectedPath; } };
        refresh.Text = "一覧を再読み込みして開く（音源の追加・削除・タグ変更後）"; refresh.AutoSize = true; refresh.Location = new Point(28, 183);
        Label dependency = new Label { Text = "FFmpeg / ffprobe を使用します。Pythonのインストールは不要です。", AutoSize = true, ForeColor = Color.FromArgb(83, 101, 122), Location = new Point(27, 220) };
        start.Text = "ライブラリを開く"; start.SetBounds(28, 253, 172, 38); start.BackColor = Color.FromArgb(23, 93, 160); start.ForeColor = Color.White; start.FlatStyle = FlatStyle.Flat;
        openBrowser.Text = "アプリ画面を開く"; openBrowser.SetBounds(213, 253, 172, 38); openBrowser.Enabled = false;
        stop.Text = "停止"; stop.SetBounds(399, 253, 92, 38); stop.Enabled = false;
        progress.SetBounds(28, 309, 662, 12); progress.Anchor = AnchorStyles.Left | AnchorStyles.Right | AnchorStyles.Bottom;
        status.SetBounds(28, 331, 662, 30); status.Anchor = AnchorStyles.Left | AnchorStyles.Right | AnchorStyles.Bottom; status.Text = "フォルダーを選択してください。専用のアプリ画面で一覧を開きます。"; status.AutoEllipsis = true;
        Controls.AddRange(new Control[] { title, hint, caption, source, browse, refresh, dependency, start, openBrowser, stop, progress, status });
        AcceptButton = start; start.Click += delegate { StartLibrary(); }; stop.Click += delegate { StopWorker(); };
        openBrowser.Click += delegate { OpenUrl(); };
        FormClosing += delegate { closing = true; if (libraryWindow != null) libraryWindow.Close(); StopWorker(); };
        if (initial != null) source.Text = initial;
        else { try { string saved = File.ReadAllText(Path.Combine(Program.DataHome, "last-folder.txt"), Encoding.UTF8).Trim(); if (Directory.Exists(saved)) source.Text = saved; } catch (IOException) { } catch (UnauthorizedAccessException) { } }
    }
    void SetRunning(bool running)
    {
        source.Enabled = !running; browse.Enabled = !running; refresh.Enabled = !running; start.Enabled = !running; stop.Enabled = running;
    }
    async void OpenUrl()
    {
        if (url == null || closing) return;
        if (libraryWindow != null) { libraryWindow.Activate(); return; }
        LibraryForm window = null;
        try
        {
            window = new LibraryForm(url); libraryWindow = window;
            window.FormClosed += delegate {
                bool returnToPicker = window.ReturnToPicker;
                if (libraryWindow == window) libraryWindow = null;
                if (closing) return;
                if (returnToPicker) { StopWorker(); Show(); Activate(); }
                else Close();
            };
            window.Show(); Hide();
            await window.InitializeAsync();
        }
        catch (Exception error)
        {
            if (closing) return;
            if (window != null && !window.IsDisposed) { window.ReturnToPicker = true; window.Close(); }
            Show();
            status.Text = "アプリ画面を起動できませんでした。";
            MessageBox.Show(this, "アプリ画面を起動できませんでした。\nMicrosoft Edge WebView2 Runtime が必要です。\nhttps://developer.microsoft.com/microsoft-edge/webview2/\n\n" + error.Message, Text, MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }
    void StartLibrary()
    {
        if (!Directory.Exists(source.Text)) { MessageBox.Show(this, "音源フォルダーを選択してください。", Text); return; }
        if (!File.Exists(Program.Python) || !File.Exists(Program.Script)) { MessageBox.Show(this, "ZIPをすべて展開し、runtimeとappを実行ファイルと同じ場所に置いてください。", Text); return; }
        try { CoreWebView2Environment.GetAvailableBrowserVersionString(); }
        catch (Exception) { MessageBox.Show(this, "Microsoft Edge WebView2 Runtime が見つかりません。\n以下のMicrosoft公式サイトからインストールしてください。\nhttps://developer.microsoft.com/microsoft-edge/webview2/", Text, MessageBoxButtons.OK, MessageBoxIcon.Information); return; }
        List<string> args = new List<string>(new string[] { "--source", Path.GetFullPath(source.Text), "--data-home", Program.DataHome, "--no-browser" });
        if (refresh.Checked) args.Add("--refresh");
        worker = new Process(); worker.StartInfo = Program.StartInfo(args.ToArray()); worker.EnableRaisingEvents = true;
        Process launched = worker;
        worker.OutputDataReceived += delegate(object sender, DataReceivedEventArgs e) { if (e.Data != null) UpdateLine(launched, e.Data); };
        worker.ErrorDataReceived += delegate(object sender, DataReceivedEventArgs e) { if (!string.IsNullOrWhiteSpace(e.Data)) UpdateLine(launched, "ERROR: " + e.Data); };
        worker.Exited += delegate { if (IsDisposed || !IsHandleCreated) return; BeginInvoke((Action)delegate { if (worker != launched) return; SetRunning(false); progress.Style = ProgressBarStyle.Continuous; if (!existingServer && launched.ExitCode == 0) status.Text = "停止しました。"; else if (existingServer) status.Text = "起動済みの別のウィンドウが一覧を管理しています。"; }); };
        url = null; existingServer = false; openBrowser.Enabled = false; status.Text = "起動しています…"; progress.Style = ProgressBarStyle.Marquee; SetRunning(true);
        try { worker.Start(); worker.BeginOutputReadLine(); worker.BeginErrorReadLine(); }
        catch (Exception error) { status.Text = error.Message; SetRunning(false); progress.Style = ProgressBarStyle.Continuous; }
    }
    void UpdateLine(Process launched, string line)
    {
        if (IsDisposed || !IsHandleCreated) return;
        BeginInvoke((Action)delegate {
            if (worker != launched || closing) return;
            if (line.StartsWith("STATE: "))
            {
                try { Dictionary<string, object> data = new JavaScriptSerializer().Deserialize<Dictionary<string, object>>(line.Substring(7)); status.Text = (string)data["message"]; if ((string)data["phase"] == "existing") existingServer = true; int total = Convert.ToInt32(data["total"]), current = Convert.ToInt32(data["current"]); if (total > 0) { progress.Style = ProgressBarStyle.Continuous; progress.Value = Math.Max(0, Math.Min(100, (int)(current * 100L / total))); } } catch { status.Text = line; }
            }
            else if (Regex.IsMatch(line, @"^URL: http://127\.0\.0\.1:\d{4,5}/?$"))
            { url = line.Substring(5); status.Text = "アプリ画面を開いています…"; progress.Style = ProgressBarStyle.Continuous; progress.Value = 100; openBrowser.Enabled = true; OpenUrl(); }
            else if (line.StartsWith("ERROR: ")) status.Text = line.Substring(7);
        });
    }
    void StopWorker()
    {
        Process running = worker; worker = null;
        if (running != null) { try { if (!running.HasExited) { running.Kill(); running.WaitForExit(3000); } } catch (InvalidOperationException) { } catch (System.ComponentModel.Win32Exception) { } finally { running.Dispose(); } }
        SetRunning(false); url = null; openBrowser.Enabled = false; progress.Style = ProgressBarStyle.Continuous; progress.Value = 0; status.Text = "停止しました。フォルダーを変更して開くこともできます。";
    }
}

sealed class LibraryForm : Form
{
    readonly WebView2 view = new WebView2(); readonly string address;
    readonly ToolStripLabel state = new ToolStripLabel("読み込み中…");
    public bool ReturnToPicker;
    public LibraryForm(string url)
    {
        address = url; Text = "音楽ライブラリ"; Icon = Program.AppIcon;
        StartPosition = FormStartPosition.CenterScreen; ClientSize = new Size(1240, 820);
        MinimumSize = new Size(880, 620); Font = new Font("Yu Gothic UI", 10F);
        ToolStrip bar = new ToolStrip { GripStyle = ToolStripGripStyle.Hidden, Padding = new Padding(8, 4, 8, 4), Dock = DockStyle.Top };
        ToolStripButton folders = new ToolStripButton("フォルダー変更・一覧の更新");
        folders.Click += delegate { ReturnToPicker = true; Close(); };
        bar.Items.Add(folders); bar.Items.Add(new ToolStripSeparator()); bar.Items.Add(state);
        view.Dock = DockStyle.Fill; Controls.Add(view); Controls.Add(bar);
        FormClosed += delegate { view.Dispose(); };
    }
    public async System.Threading.Tasks.Task InitializeAsync()
    {
        string cache = Path.Combine(Program.DataHome, "WebView2");
        CoreWebView2Environment environment = await CoreWebView2Environment.CreateAsync(null, cache, null);
        if (IsDisposed) return;
        await view.EnsureCoreWebView2Async(environment);
        if (IsDisposed) return;
        view.CoreWebView2.Settings.AreDevToolsEnabled = false;
        view.CoreWebView2.Settings.IsStatusBarEnabled = false;
        view.CoreWebView2.Settings.AreDefaultContextMenusEnabled = false;
        view.CoreWebView2.Settings.IsWebMessageEnabled = false;
        view.CoreWebView2.NewWindowRequested += delegate(object sender, CoreWebView2NewWindowRequestedEventArgs e) { e.Handled = true; };
        view.CoreWebView2.NavigationStarting += delegate(object sender, CoreWebView2NavigationStartingEventArgs e) {
            Uri destination, origin = new Uri(address);
            if (!Uri.TryCreate(e.Uri, UriKind.Absolute, out destination) || destination.Scheme != origin.Scheme || destination.Host != origin.Host || destination.Port != origin.Port) e.Cancel = true;
        };
        view.CoreWebView2.NavigationCompleted += delegate(object sender, CoreWebView2NavigationCompletedEventArgs e) { state.Text = e.IsSuccess ? "音楽ライブラリ" : "読み込めませんでした。フォルダー選択画面から開き直してください。"; };
        view.CoreWebView2.Navigate(address);
    }
}
