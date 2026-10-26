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
