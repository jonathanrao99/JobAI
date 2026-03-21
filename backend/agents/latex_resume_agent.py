"""
backend/agents/latex_resume_agent.py
=====================================
Renders LLM-tailored JSON into a LaTeX resume and compiles to PDF.
Uses the user's custom template (clean single-column, ATS-friendly).
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Optional

from loguru import logger

# ── LaTeX escaping ────────────────────────────────────────────────

_LATEX_SPECIAL = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}


def _esc(text: str) -> str:
    if not text:
        return ""
    out: list[str] = []
    for ch in text:
        out.append(_LATEX_SPECIAL.get(ch, ch))
    result = "".join(out)
    result = result.replace("\u2013", "--")    # en-dash
    result = result.replace("\u2014", "---")   # em-dash
    result = result.replace("\u2018", "`")     # left single quote
    result = result.replace("\u2019", "'")     # right single quote
    result = result.replace("\u201c", "``")    # left double quote
    result = result.replace("\u201d", "''")    # right double quote
    result = result.replace("\u2022", "")      # bullet char
    result = result.replace("\u2023", "")      # triangle bullet
    result = result.replace("\u223c", r"$\sim$")  # tilde operator
    result = result.replace("\u2248", r"$\approx$")
    return result


def _bold_metrics(text: str) -> str:
    """After escaping, wrap numbers+% in \\textbf for emphasis."""
    text = re.sub(r"([>~]?\d+[\.,]?\d*\\%\+?)", r"\\textbf{\1}", text)
    text = re.sub(r"(\d+[xX]\s)", r"\\textbf{\1}", text)
    return text


def _fmt(text: str) -> str:
    return _bold_metrics(_esc(text.strip()))


# ── Template constants ────────────────────────────────────────────

_HEAD = r"""\documentclass[10pt,letterpaper]{article}

\usepackage[
  top=0.5in,
  bottom=0.5in,
  left=0.65in,
  right=0.65in
]{geometry}

\usepackage[T1]{fontenc}
\usepackage[utf8]{inputenc}
\usepackage{lmodern}
\usepackage{tabularx}
\usepackage{enumitem}
\usepackage{hyperref}
\usepackage{titlesec}
\usepackage{xcolor}

\definecolor{accent}{HTML}{1F4E8C}
\definecolor{muted}{HTML}{555555}
\definecolor{dark}{HTML}{1A1A1A}

\hypersetup{colorlinks=true, urlcolor=accent}

\pagestyle{empty}
\setlength{\parindent}{0pt}
\setlist[itemize]{
  leftmargin=11pt, nosep, topsep=2pt, itemsep=1pt,
  label=\small$\circ$
}

\titleformat{\section}{\bfseries\small\color{accent}}
  {}{0pt}{\MakeUppercase}[\vspace{1pt}{\color{dark}\titlerule[0.4pt]}\vspace{1pt}]
\titlespacing{\section}{0pt}{6pt}{3pt}

\newcommand{\roleheading}[2]{%
  \begin{tabularx}{\linewidth}{@{}X r@{}}
    \textbf{\small\color{dark}#1} & \small\textcolor{muted}{#2}
  \end{tabularx}\vspace{-1pt}\par
}
\newcommand{\orgline}[2]{%
  \begin{tabularx}{\linewidth}{@{}X r@{}}
    \textit{\footnotesize\textcolor{muted}{#1}} &
    \textit{\footnotesize\textcolor{muted}{#2}}
  \end{tabularx}\vspace{1pt}\par
}
\newcommand{\toolsline}[1]{%
  \textit{\footnotesize\textcolor{muted}{#1}}\vspace{2pt}\par
}
\newcommand{\skillrow}[2]{%
  \noindent{\footnotesize\textbf{#1:} #2}\par\vspace{1pt}
}

\begin{document}

% ── HEADER ────────────────────────────────────────────────────────
\begin{center}
  {\LARGE\textbf{Jonathan Abhishek Rao Thota}}\\[4pt]
  \small\textcolor{muted}{%
    Houston, TX \;$|$\;
    \href{tel:+12055030985}{+1 205-503-0985} \;$|$\;
    \href{mailto:jonathanrao5576@gmail.com}{jonathanrao5576@gmail.com} \;$|$\;
    \href{https://jonathanthota.vercel.app}{jonathanthota.vercel.app}
  }\\[2pt]
  \small\textcolor{muted}{%
    \href{https://linkedin.com/in/jonathanrao99}{linkedin.com/in/jonathanrao99} \;$|$\;
    \href{https://github.com/jonathanrao99}{github.com/jonathanrao99} \;$|$\;
    \textit{OPT Authorized}
  }
\end{center}

\vspace{-14pt}
"""

_SKILLS = r"""
% ── SKILLS ────────────────────────────────────────────────────────
\section{Technical Skills}

\skillrow{ML \& DL}{Model Training, Hyperparameter Tuning, Transfer Learning, Model Compression, CNNs, LSTM, MobileNetV2, Feature Engineering, Cross-Validation}
\skillrow{GenAI \& LLMs}{LangChain, OpenAI API, OpenRouter, Multi-Agent Orchestration, Prompt Engineering, RAG Pipelines, ChromaDB, Vector Embeddings}
\skillrow{Libraries}{TensorFlow/Keras, Scikit-learn, XGBoost, LightGBM, OpenCV, Pandas, NumPy}
\skillrow{Languages}{Python, SQL, JavaScript, TypeScript, R}
\skillrow{Infrastructure}{REST APIs, Flask, FastAPI, Docker, AWS, ETL Pipelines, PostgreSQL, MySQL, Git/GitHub, Jupyter}
\skillrow{Visualization}{Matplotlib, Seaborn, Plotly, Streamlit, Tableau, Power BI}
"""

_EDUCATION = r"""
% ── EDUCATION ─────────────────────────────────────────────────────
\section{Education}

\roleheading{Texas A\&M University -- Victoria}{Jan 2025 -- May 2026}
\orgline{M.S. Data Science \;|\; GPA: 3.8 / 4.0}{Houston, TX}
\vspace{1pt}
\footnotesize\textit{Statistical Modeling, Predictive Analytics, Machine Learning, Data
Visualization, Database Systems, Advanced SQL, Research Methods}

\end{document}
"""


# ── Section builders ──────────────────────────────────────────────


def _build_summary(summary: str) -> str:
    if not summary or not summary.strip():
        return ""
    return (
        "\n% ── SUMMARY ───────────────────────────────────────────────────────\n"
        "\\section{Summary}\n\n"
        "\\footnotesize\n"
        f"{_esc(summary.strip())}\n"
    )


def _build_experience(
    llm_exp: list[dict[str, Any]],
    meta: list[dict[str, str]],
) -> str:
    if not llm_exp:
        return ""
    lines: list[str] = [
        "\n% ── EXPERIENCE ────────────────────────────────────────────────────\n",
        "\\section{Experience}\n\n",
    ]
    for i, entry in enumerate(llm_exp):
        if not isinstance(entry, dict):
            continue
        if i < len(meta):
            role = meta[i]["role"]
            dates = meta[i]["dates"].replace("\u2013", "--")
            company = meta[i]["company"]
            location = meta[i]["location"]
        else:
            role = entry.get("role", "")
            company = entry.get("company", "")
            dates, location = "", ""

        lines.append(f"\\roleheading{{{_esc(role)}}}{{{_esc(dates)}}}\n")
        lines.append(f"\\orgline{{{_esc(company)}}}{{{_esc(location)}}}\n")

        bullets = [
            str(b).strip()
            for b in (entry.get("bullets") or [])
            if b and str(b).strip() and len(str(b).strip()) >= 10
        ]
        if bullets:
            lines.append("\\begin{itemize}\\footnotesize\n")
            for b in bullets:
                lines.append(f"  \\item {_fmt(b)}\n")
            lines.append("\\end{itemize}\n")

        if i < len(llm_exp) - 1:
            lines.append("\n\\vspace{3pt}\n\n")

    return "".join(lines)


def _build_projects(
    llm_proj: list[dict[str, Any]],
    meta: list[dict[str, str]],
) -> str:
    if not llm_proj:
        return ""
    lines: list[str] = [
        "\n% ── PROJECTS ──────────────────────────────────────────────────────\n",
        "\\section{Projects}\n\n",
    ]
    for i, pj in enumerate(llm_proj):
        if not isinstance(pj, dict):
            continue
        raw_name = (pj.get("name") or "").strip()
        name = raw_name.split("\t")[0].strip()
        tech = (pj.get("tech") or "").strip()

        if i < len(meta):
            if not name:
                name = meta[i]["name"]
            if not tech:
                tech = meta[i]["tech"]

        lines.append(
            f"\\roleheading{{{_esc(name)}}}"
            f"{{\\href{{https://github.com/jonathanrao99}}{{GitHub}}}}\n"
        )
        if tech:
            lines.append(f"\\toolsline{{{_esc(tech)}}}\n")

        bullets = [
            str(b).strip()
            for b in (pj.get("bullets") or [])
            if b and str(b).strip() and len(str(b).strip()) >= 10
        ]
        if bullets:
            lines.append("\\begin{itemize}\\footnotesize\n")
            for b in bullets:
                lines.append(f"  \\item {_fmt(b)}\n")
            lines.append("\\end{itemize}\n")

        if i < len(llm_proj) - 1:
            lines.append("\n\\vspace{2pt}\n\n")

    return "".join(lines)


# ── Public API ────────────────────────────────────────────────────


def render_latex_resume(
    llm_data: dict,
    experience_meta: list[dict[str, str]],
    project_meta: list[dict[str, str]],
) -> str:
    summary = _build_summary(llm_data.get("summary", ""))
    experience = _build_experience(llm_data.get("experience", []), experience_meta)
    projects = _build_projects(llm_data.get("projects", []), project_meta)
    return _HEAD + summary + _SKILLS + experience + projects + _EDUCATION


def compile_pdf(
    tex_content: str,
    out_dir: Path,
    basename: str,
) -> tuple[Path, Optional[Path]]:
    out_dir.mkdir(parents=True, exist_ok=True)
    tex_path = out_dir / f"{basename}.tex"
    tex_path.write_text(tex_content, encoding="utf-8")

    compiler = shutil.which("tectonic") or shutil.which("pdflatex")
    if not compiler:
        logger.warning(
            "No TeX compiler found — .tex saved but PDF not compiled. "
            "Install: brew install tectonic"
        )
        return tex_path, None

    try:
        if "tectonic" in compiler:
            cmd = [compiler, "--outdir", str(out_dir), str(tex_path)]
        else:
            cmd = [
                compiler,
                "-interaction=nonstopmode",
                f"-output-directory={out_dir}",
                str(tex_path),
            ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        pdf_path = out_dir / f"{basename}.pdf"
        if pdf_path.exists():
            for ext in (".aux", ".log", ".out", ".synctex.gz"):
                aux = out_dir / f"{basename}{ext}"
                if aux.exists():
                    aux.unlink()
            logger.info(f"PDF compiled: {pdf_path}")
            return tex_path, pdf_path
        else:
            logger.error(
                f"TeX compile failed.\nstdout: {result.stdout[-600:]}\nstderr: {result.stderr[-600:]}"
            )
            return tex_path, None
    except subprocess.TimeoutExpired:
        logger.error("TeX compilation timed out (120s)")
        return tex_path, None
    except Exception as e:
        logger.error(f"TeX compile error: {e}")
        return tex_path, None
