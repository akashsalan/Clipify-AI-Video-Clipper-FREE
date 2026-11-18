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
[assembly: AssemblyVersion("3.2.1.0")]
[assembly: AssemblyFileVersion("3.2.1.0")]

namespace ClipifyAI
{
    static class Program
    {
        [STAThread]
        static int Main(string[] args)
        {
            string baseDir = AppDomain.CurrentDomain.BaseDirectory;
            string mainPy = Path.Combine(baseDir, "main.py");
            
            // Prefer dedicated AI runtime matching Python 3.11
            string pythonExe = FindPythonInterpreter(baseDir);
            
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

        static string FindPythonInterpreter(string baseDir)
        {
            string runtimeEnv = Environment.GetEnvironmentVariable("CLIPPEDAI_RUNTIME");
            if (!string.IsNullOrEmpty(runtimeEnv))
            {
                string envPy = Path.Combine(runtimeEnv, "Scripts", "python.exe");
                if (File.Exists(envPy)) return envPy;
            }

            string[] candidates = new string[]
            {
                Path.Combine(baseDir, "runtime", "Scripts", "python.exe"),
                Path.Combine(baseDir, "..", "runtime", "Scripts", "python.exe"),
                Path.Combine(baseDir, ".venv", "Scripts", "python.exe"),
                Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Programs", "ClipifyAI", "runtime", "Scripts", "python.exe"),
                Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Programs", "ClipifyAI", "python311", "python.exe"),
                @"L:\tester\runtime\Scripts\python.exe",
                @"L:\clipp tester\runtime\Scripts\python.exe",
                @"C:\Python311\python.exe",
                @"C:\Program Files\Python311\python.exe"
            };

            foreach (string candidate in candidates)
            {
                if (File.Exists(candidate))
                {
                    return candidate;
                }
            }

            return "python.exe";
        }
    }
}
