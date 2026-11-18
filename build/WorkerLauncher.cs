using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;

[assembly: AssemblyTitle("Clipify AI Worker Launcher")]
[assembly: AssemblyDescription("Clipify AI Video Clipper Background Worker")]
[assembly: AssemblyConfiguration("")]
[assembly: AssemblyCompany("Clipify AI")]
[assembly: AssemblyProduct("Clipify AI")]
[assembly: AssemblyCopyright("Copyright © 2026 Clipify AI")]
[assembly: AssemblyTrademark("")]
[assembly: AssemblyCulture("")]
[assembly: ComVisible(false)]
[assembly: AssemblyVersion("3.1.0.0")]
[assembly: AssemblyFileVersion("3.1.0.0")]

namespace ClipifyAI
{
    static class Program
    {
        [STAThread]
        static int Main(string[] args)
        {
            string baseDir = AppDomain.CurrentDomain.BaseDirectory;
            string mainPy = Path.Combine(baseDir, "main.py");
            
            // Prefer dedicated AI runtime
            string pythonExe = Path.Combine(baseDir, "runtime", "Scripts", "python.exe");
            if (!File.Exists(pythonExe))
            {
                pythonExe = Path.Combine(baseDir, ".venv", "Scripts", "python.exe");
            }
            if (!File.Exists(pythonExe))
            {
                pythonExe = "python.exe";
            }
            
            ProcessStartInfo psi = new ProcessStartInfo();
            psi.FileName = pythonExe;
            
            string combinedArgs = "-u \"" + mainPy + "\"";
            if (args != null && args.Length > 0)
            {
                for (int i = 0; i < args.Length; i++)
                {
                    combinedArgs += " \"" + args[i].Replace("\"", "\\\"") + "\"";
                }
            }
            
            psi.Arguments = combinedArgs;
            psi.WorkingDirectory = baseDir;
            psi.UseShellExecute = false;
            
            try
            {
                using (Process proc = Process.Start(psi))
                {
                    if (proc == null) return 1;
                    proc.WaitForExit();
                    return proc.ExitCode;
                }
            }
            catch (Exception ex)
            {
                Console.Error.WriteLine("Clipify AI worker launcher error: " + ex.Message);
                return 1;
            }
        }
    }
}
