# Traditional Chinese Telegram output

更新：2026-10-26（Asia/Taipei）；基準 d0fe412；分支 main。
範圍：Telegram 共用發送層、文字轉換模組、依賴、離線測試與中英文文件。
已核對 hook ahead=0/behind=0、PROJECT_STATUS、CONTRIBUTING、bot identity handoff、實際 tg 與全部發送入口。其他 handoff 保留。
原因：來源摘錄直接輸出原文，AI 的繁體提示不涵蓋此路徑。
決策：OpenCC s2tw 做字形轉換，共用發送前套用；保留 HTML tags/attributes、URL、code/pre。只處理顯示，不改 archive、追蹤詞與原始資料；不新增模型呼叫。
已實作：chinese_output.py 使用 OpenCC 0.1.7 s2tw；tg 發送前轉換，HTML fallback 沿用轉換結果；中英文文件與 runtime/lock 依賴同步。
已驗證：352 項完整離線測試與 Ruff 通過；九個新增測試案例涵蓋截圖字形、數值、英文、HTML attributes、URLs、entities、code/pre、兩個 bot 與 400 retry。
完整 suite 同時發現 menu 模組捕捉本機 token 讓其他 listener 測試碰到新網路入口，conftest 統一將 menu token 設空以隔離，menu 專屬測試另注入假值。
限制：詞義與內容不重新分析；code/pre 與 URL 原樣保留；舊 Telegram 訊息不回溯修改。未部署，目前 running workflow 仍是舊版本。
commit/push：9c6e02a 已推送 origin/main；GitHub CI run 40314888616 成功：https://github.com/Yili-code/Crypto-Flash/actions/runs/40314888616 。目前未部署新版本。
