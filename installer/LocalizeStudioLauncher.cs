// Small Windows GUI launcher for the self-contained offline package.
// It deliberately uses only the .NET Framework APIs built into supported Windows versions.
using System;
using System.Diagnostics;
using System.IO;
using Microsoft.Win32;
using System.Reflection;
using System.Windows.Forms;

internal static class LocalizeStudioLauncher
{
    private const string ApplicationName = "Localize Studio";
    private const string UninstallRegistryKey =
        @"Software\Microsoft\Windows\CurrentVersion\Uninstall\{96FB8698-9622-4824-9224-87C402D0BA9E}_is1";

    [STAThread]
    private static int Main(string[] args)
    {
        string root = ResolveInstallationRoot();
        if (String.IsNullOrEmpty(root))
        {
            ShowError("Unable to locate the installation directory.");
            return 1;
        }

        string error;
        if (!TryBuildLaunchContext(root, out error))
        {
            if (!HasArgument(args, "--verify"))
            {
                ShowError(error);
            }
            return 1;
        }

        if (HasArgument(args, "--verify"))
        {
            return 0;
        }

        try
        {
            ProcessStartInfo startInfo = new ProcessStartInfo();
            startInfo.FileName = Path.Combine(root, "runtime", "python", "pythonw.exe");
            startInfo.Arguments = Quote(Path.Combine(root, "app", "localizer_gui.pyw"));
            startInfo.WorkingDirectory = EnsureProjectsDirectory();
            startInfo.UseShellExecute = false;
            startInfo.CreateNoWindow = true;
            Process.Start(startInfo);
            return 0;
        }
        catch (Exception exception)
        {
            ShowError("The desktop application could not be started.\r\n\r\n" + exception.Message);
            return 1;
        }
    }

    private static string ResolveInstallationRoot()
    {
        string ownDirectory = Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location);
        if (String.IsNullOrEmpty(ownDirectory))
        {
            return String.Empty;
        }
        if (File.Exists(Path.Combine(ownDirectory, "runtime", "python", "pythonw.exe")))
        {
            return ownDirectory;
        }

        try
        {
            using (RegistryKey key = Registry.CurrentUser.OpenSubKey(UninstallRegistryKey))
            {
                string installed = key == null ? null : key.GetValue("InstallLocation") as string;
                if (!String.IsNullOrEmpty(installed))
                {
                    return installed.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
                }
            }
        }
        catch (Exception)
        {
            // The validation below reports a concise user-facing error without exposing registry details.
        }
        return ownDirectory;
    }

    private static bool TryBuildLaunchContext(string root, out string error)
    {
        string python = Path.Combine(root, "runtime", "python", "pythonw.exe");
        string gui = Path.Combine(root, "app", "localizer_gui.pyw");
        string ffmpeg = Path.Combine(root, "runtime", "ffmpeg", "bin", "ffmpeg.exe");
        string ffprobe = Path.Combine(root, "runtime", "ffmpeg", "bin", "ffprobe.exe");
        string models = Path.Combine(root, "models");
        string fonts = Path.Combine(root, "fonts");

        foreach (string required in new[] { python, gui, ffmpeg, ffprobe, models, fonts })
        {
            if (!File.Exists(required) && !Directory.Exists(required))
            {
                error = "This installation is incomplete. Missing: " + required +
                    "\r\n\r\nRun Verify YouTube Localizer Installation or reinstall the package.";
                return false;
            }
        }

        string tier = ReadPackageTier(root);
        if (tier != "standard" && tier != "complete")
        {
            error = "The installation package tier is invalid. Reinstall the application.";
            return false;
        }

        Environment.SetEnvironmentVariable("YOUTUBE_LOCALIZER_HOME", root);
        Environment.SetEnvironmentVariable("YOUTUBE_LOCALIZER_MODELS", models);
        Environment.SetEnvironmentVariable("YOUTUBE_LOCALIZER_FONTS", fonts);
        Environment.SetEnvironmentVariable("YOUTUBE_LOCALIZER_PACKAGE_TIER", tier);
        Environment.SetEnvironmentVariable("FFMPEG_PATH", ffmpeg);
        Environment.SetEnvironmentVariable("FFPROBE_PATH", ffprobe);

        string path = Path.Combine(root, "runtime", "ffmpeg", "bin") + ";" +
            (Environment.GetEnvironmentVariable("PATH") ?? String.Empty);
        if (tier == "complete")
        {
            string ollama = Path.Combine(root, "runtime", "ollama", "ollama.exe");
            if (!File.Exists(ollama))
            {
                error = "The Complete package is missing its local AI runtime. Reinstall the Complete package.";
                return false;
            }
            Environment.SetEnvironmentVariable("OLLAMA_PATH", ollama);
            path = Path.Combine(root, "runtime", "ollama", "lib", "ollama", "cuda_v12") + ";" +
                Path.Combine(root, "runtime", "ollama") + ";" + path;
        }
        else
        {
            Environment.SetEnvironmentVariable("OLLAMA_PATH", null);
        }
        Environment.SetEnvironmentVariable("PATH", path);

        error = String.Empty;
        return true;
    }

    private static string ReadPackageTier(string root)
    {
        string path = Path.Combine(root, "package-tier.txt");
        if (!File.Exists(path))
        {
            return String.Empty;
        }
        return File.ReadAllText(path).Trim().ToLowerInvariant();
    }

    private static string EnsureProjectsDirectory()
    {
        string projects = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments),
            "YouTube Localizer Projects");
        Directory.CreateDirectory(projects);
        return projects;
    }

    private static bool HasArgument(string[] args, string value)
    {
        foreach (string argument in args)
        {
            if (String.Equals(argument, value, StringComparison.OrdinalIgnoreCase))
            {
                return true;
            }
        }
        return false;
    }

    private static string Quote(string value)
    {
        return "\"" + value.Replace("\"", "\\\"") + "\"";
    }

    private static void ShowError(string message)
    {
        MessageBox.Show(message, ApplicationName, MessageBoxButtons.OK, MessageBoxIcon.Error);
    }
}
