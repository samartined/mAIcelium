# Prompt: Debug an issue

## Template
I have the following error/problem: {{DESCRIPTION}}

Context: {{CONTEXT}}
Relevant logs: {{LOGS}}

## Agent instructions
1. Mentally reproduce the flow causing the error
2. Identify the components involved
3. Formulate hypotheses ranked by probability
4. Propose verification steps for each hypothesis
5. Suggest a fix with an explanation of why it works
6. If the finding is relevant, propose documenting it in techcorpus
