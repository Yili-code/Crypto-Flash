# Concise Heimdall messages

更新：2026-10-26（Asia/Taipei）；分支main；基準0ed27c1。
授權：使用者要求移除一般使用者不在意的資訊、簡化詳細回覆；後續明確指定改3.5 Flash-Lite，屬同任務追加，不取消回覆精簡。
已讀PROJECT_STATUS、CONTRIBUTING、相關handoff、news/digest/tracking/QA/flash實作與格式測試；hook ahead0/behind0，tracked乾淨。
模型：已設定並讀回GitHub GEMINI_MODEL/GEMINI_SEARCH_MODEL皆gemini-3.5-flash-lite，不開billing，不宣稱免費grounding已修復。
範圍：常用新聞查詢、重要摘要、日報、追蹤與QA呈現；保留來源/時間、失敗/缺資料與必要不確定性，篩選/配額/送達進度不變。/health保留實際問題與嚴重性，隱藏零計數/重複技術資訊；CLI診斷不變。特定事件前長分析格式不在本次一般指令呈現變更內。
已實作：news/search/important去除固定筆數、時區、內部分級與處理註記，保留時間/來源；重要摘要每筆上限由600改280字，來源摘錄160改120字；tracking清除冗長footer及內部分級但保留跨主題標籤與更多結果提示；daily digest移除固定宣傳/資料處理footer，只在實際漏入/未分級時短警告；QA改為簡單問答1–3句、解釋按需3點，80–180字目標且保留條件與不確定性；CRITICAL標籤改人類可理解的重大消息。/health以繁中顯示實際問題、critical仍優先，CLI完整診斷未改。
已驗證：375項完整離線測試通過（5.04s），Ruff通過；測試含來源/HTML/字數、無資料/失敗、追蹤分頁ack、日報合格來源與實際省略警告、健康錯誤可見但不暴露內部路徑。格式預覽 .tmp/heimdall-message-preview.md 使用示例資料，無真實Telegram發送。
模型設定：主模型與搜尋模型均為3.5 Flash-Lite，已實際讀回；免費grounding限制仍在，不因文字精簡宣稱YouTube修復。
commit/push/deploy：準備提交推送並核對CI；本次文字修改尚未部署，依AGENTS部署需另獲授權。
