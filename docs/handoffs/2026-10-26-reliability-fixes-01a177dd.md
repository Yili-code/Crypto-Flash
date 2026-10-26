# YouTube and owner access repairs

更新：2026-10-26（Asia/Taipei）；分支 main；基準 aabd4d0。
授權：使用者要求解決完整功能測試發現的 YouTube 429、Bankless RSS 404 與 owner allowlist。
已讀 PROJECT_STATUS、full-function handoff、實際 Gemini/policy/YouTube/auth 程式與測試；hook ahead=0/behind=0，tracked 乾淨。無其他 active 手改程式。
決策：三個問題分 atomic commits。Bankless ID 大小寫校正；owner secret 設為已核對使用者，程式 fail closed；429 先加安全結構化錯誤診斷，依真實 quota 再修復，不改模型/關查證/清除日配額。
證據：Bankless 舊 UCAI9... HTTP404，正確 UCAl9... HTTP200，Atom title=Bankless。本機 Telegram 設定仍是 Test group，非 production，僅用 getChatAdministrators 核對 creator 名字與既有 YiLi 身分；不把本機群組狀態當 production。
狀態：實作中。owner ID 不寫入 repo/log。
commit/push/deploy：待完成；所有外部操作另記驗證結果。

階段：Bankless 修正 821ca33 已推送；安全 quota 診斷實作完成，33 項相關測試與 Ruff 通過，準備正式 YouTube 執行核對真正的 429 metric。

Owner：已依唯一匹配的 creator 名字/username 核對使用者，將 ID 加密更新 GitHub TELEGRAM_OWNER_USER_IDS secret，metadata 更新成功（2026-10-26T11:49:21Z）。ID 未輸出或存入 repo。程式改為空 allowlist deny，付費/管理功能不再 fail open；準備測試與重啟。

429 根因：正式 run 40317861029/job 121554882131 operation=search、model=gemini-3.5-flash-lite、limits=[]。AI Studio 新聞服務專案顯示 Free tier；Google 官方 pricing 明載 3.5 Flash-Lite free tier Search grounding unavailable（https://ai.google.dev/gemini-api/docs/pricing#gemini-3.5-flash-lite）。已向使用者詢問僅查證使用 2.5 Flash-Lite 或啟用付費，尚未收到選擇，不切換模型/啟用帳務。
已準備可選 GEMINI_SEARCH_MODEL（預設主模型，不偷偷切換）；單獨搜尋路由保留 grounding/引文校驗與每日計數，待驗證。
自動審查拒絕 key lookup URL 查法（含金鑰 query）；未執行、未繞過，改以 AI Studio 可見 UI 查證。
Owner fail-closed 已推送 3e238f1，先前 357 項完整測試/Ruff 通過；正在安全重啟常駐服務使 secret 生效。

## 已驗證階段結果（2026-10-26 20:00 Asia/Taipei）
- Bankless 修正後連網複查六個 YouTube RSS 均 HTTP200；五個新聞 RSS 與日曆抓取均成功。
- Owner fail-closed + secret 已部署：run 40318803031 / job 121559598328，head 3f2329b；setup/dependencies success，正式服務 in_progress。此前排隊數分鐘，受控重排檢查時已自行進入 running，因此沒有 cancel/重複 dispatch。
- Unigram 真實 /health 在20:00成功回覆 YiLi，Critical0/Warning1；owner allowlist warning 已消失，僅剩 YouTube pending162。非 owner/空 allowlist 拒絕由離線測試驗證，未借用他人帳號。
- 全套362項測試通過（4.91s）、Ruff通過；GitHub CI 40318742086 成功。
- 429正式證據：operation=search，gemini-3.5-flash-lite；Google官方定價免費API不支援Search grounding，並非一般重試可解。官方來源 https://ai.google.dev/gemini-api/docs/pricing#gemini-3.5-flash-lite 。
- 可選 GEMINI_SEARCH_MODEL 路由已完成並部署（空值仍主模型），影片摘要維持主模型、grounding引用驗證與當日計數保留。尚未設定新值，等待使用者選擇「只查證改2.5 Flash-Lite免費」或「3.5開付費」。未更換模型、未開billing、未關查證、未清除配額。
- 未完成：YouTube 完整摘要+查證送達需上述模型/帳務選擇，不能宣稱全部問題已修復。162 pending 未刪除或假標完成。
下一步：收到明確選擇後設定 GitHub GEMINI_SEARCH_MODEL 或由使用者完成billing，再執行一次正式YT驗證至實際送達、檢查續傳與pending變化；依新變更跑相應測試。
commit/push：821ca33來源修復、774f89f安全診斷、3e238f1權限修復、fac3020範例修正、3f2329b可選搜尋路由均已推送；本紀錄另提交保存結果。
