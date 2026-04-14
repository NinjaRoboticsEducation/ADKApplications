Annotate difficult Japanese words, phrases, and grammar patterns in this text for intermediate learners.

Actions:
1. Insert sequential *1, *2, *3 markers after difficult expressions in the text.
2. After the text, add a --- separator.
3. Add heading: ### 言葉の解説 (Glossary)
4. For each marker, write an entry with:
   - 意味 (Meaning): Explain the nuance in Japanese.
   - 例文 (Examples): 1-2 natural example sentences.
   - 比較 (Comparison): Compare with a similar/contrasting expression.

What to annotate:
- Advanced grammar patterns (〜はおろか, 〜ざるを得ない, etc.)
- Idiomatic phrases and set expressions
- Formal or abstract vocabulary hard to infer from context
- Patterns whose nuance differs from simpler synonyms

Rules:
- Do NOT over-annotate basic words.
- Place marker after the full expression, not each component.
- If the phrase has furigana, place marker after: 表現（ひょうげん）*1
- Keep numbering sequential.
- Do NOT change the original text except for inserting *N markers.
- Annotate 10-20 items per ~2000 characters.

Example:
Input: 彼の成功は努力のおかげであり、その結果に相違ない。
Output:
彼の成功は努力のおかげで*1あり、その結果に相違ない*2。

---

### 言葉の解説 (Glossary)

1. 〜おかげで
* **意味 (Meaning):** ある良い結果が特定の原因によってもたらされたことを示す。
* **例文 (Examples):**
  * 友達が助けてくれたおかげで、宿題が終わりました。
  * 毎日練習したおかげで、上手に話せるようになりました。
* **比較 (Comparison):**
  * **「〜せいで」との違い:** おかげでは良い結果、せいでは悪い結果に使う。

Return the full annotated text with the glossary appendix.
