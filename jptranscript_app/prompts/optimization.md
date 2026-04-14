Clean this Japanese transcript. Apply these edits in order:

1. Preserve timestamps like [00:15:30], 0:15, or 2:38 exactly when they are part of the transcript structure. Remove only obvious subtitle counters and non-content tags.
2. Fix unnatural spacing between characters or words.
3. Remove semantically empty fillers: あのー, えーっと, まあ, ええ, その (when clearly padding).
4. Remove sentence-ending fillers like ですね, ですよね only when they are padding, not meaning.
5. Keep words that carry tone, hesitation, emphasis, or nuance. Treat なんか conservatively.
6. Correct only obvious typos, particle mistakes, and clearly broken grammar.
7. Normalize lightly from spoken to written Japanese only when meaning stays identical.

Hard rules:
- Preserve 100% of the content meaning and completeness.
- Do NOT summarize, compress, rewrite, or add content.
- Keep speaker labels (e.g., 鈴木さん:), names, numbers, dates exactly.
- Keep every timestamp line exactly once and in order.
- When uncertain, keep the original wording.

Example:
Input: [00:02:10] 鈴木さん: あのー、まあ、昨日の会議ですけどね、えーっと、配布したその資料が、なんか少し間違ってたんですよね。
Output: 鈴木さん: 昨日の会議ですが、配布した資料がなんか少し間違っていました。

Return only the cleaned transcript.
