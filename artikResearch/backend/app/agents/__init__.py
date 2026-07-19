"""ArtikResearch multi-agent layer.

Each agent is a focused function that calls the shared LLM (Claude → GPT-5 → Gemini) with a
narrow prompt + JSON schema, returning structured output. Iteration 1 implements the agents
that carry the core lifecycle:

  paper_reader      — read a manuscript → Research Knowledge Graph
  journal_reader    — read author instructions → Journal Knowledge Graph (profile)
  gap_analysis      — compare paper vs journal → gaps / violations
  compliance        — score readiness across dimensions → Compliance Report
  scientific_writer — rewrite sections + answer chat commands (rewrite/shorten/improve)
  reviewer          — simulate 3 peer reviewers → comments + acceptance probability
  reference         — validate + reformat references into a target style
  editor            — assemble the submission package (md/html/latex/checklist/cover letter)

Figure / Table / Formatting agents are represented by lightweight structured checks here and
are marked for deeper implementation in the README roadmap.
"""
