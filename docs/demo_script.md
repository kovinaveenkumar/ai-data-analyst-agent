# 2-minute demo video script

Record with OBS or Loom at 1080p. Rehearse twice. Keep the browser zoom at 110% so text is readable.

| Time | Show | Say (roughly) |
|---|---|---|
| 0:00-0:15 | App home screen | "Business teams wait days for simple data answers. I built an AI analyst that answers them in seconds, and shows its work so people can trust it." |
| 0:15-0:40 | Ask "What was monthly revenue in 2025?" | "Claude writes the SQL, a validator checks it, and it runs through a read-only MCP server. Here is the answer, the chart, and the exact SQL." Open the SQL expander. |
| 0:40-1:05 | Ask a hard question, e.g. "What is the return rate by category?" then open "How the agents worked it out" | "If a query fails or the validator spots a problem, the reason goes back to the SQL writer and it retries. You can see every step." Show a retry if one happened. |
| 1:05-1:20 | Download the PDF; open it | "Every answer exports as a PDF report." |
| 1:20-1:35 | Reports tab -> Generate Monthly Sales Report | "Repeatable reports are Agent Skills, which also work inside Claude Code." |
| 1:35-1:50 | Terminal: `pytest` passing; README evaluation table | "Security tests prove the agent can't modify data, and a 30-question evaluation measures accuracy: X% with the validator versus Y% without." |
| 1:50-2:00 | Architecture diagram | "Claude API, MCP, PostgreSQL, Streamlit. Link to the code is below." |

Replace X and Y with your real evaluation numbers.
