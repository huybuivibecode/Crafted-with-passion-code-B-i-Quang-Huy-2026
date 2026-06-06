# Instruction

## Skill
Trong dự án POD Fulfillment này, `Skill` là năng lực nghiệp vụ mà assistant cần thể hiện khi hỗ trợ seller. Skill cốt lõi gồm: gợi ý sản phẩm phù hợp theo market, so sánh sản phẩm theo partner, màu, giá, location, kiểm tra tồn kho, và hỗ trợ chuẩn bị flow tạo đơn. Skill phải ưu tiên tính thực tế cho seller POD, không trả lời lan man.

## Tool
`Tool` là các công cụ vận hành để agent làm việc với hệ thống BurgerPrints và codebase. Tool dùng để đọc dữ liệu sản phẩm, truy vấn API, lọc variations, kiểm tra out-of-stock, đọc lịch sử chat, sửa code, kiểm tra lỗi và chạy xác minh. Tool giúp câu trả lời có dữ liệu thật, có thể kiểm chứng, thay vì suy đoán chung chung.

## Agent
`Agent` là bộ điều phối trung tâm của workflow. Agent nhận câu hỏi người dùng, phân tích intent, trích xuất tiêu chí như market, partner, màu, giá, SKU, rồi điều hướng sang đúng nhánh xử lý: tư vấn, so sánh, stock check hoặc order support. Sau đó agent tổng hợp dữ liệu từ BurgerPrints, tạo câu trả lời rõ ràng bằng tiếng Việt, dễ đọc như trải nghiệm ChatGPT.

Tóm tắt:
- Skill: hiểu đúng bài toán POD seller
- Tool: lấy và xử lý dữ liệu thật
- Agent: điều phối toàn bộ workflow đầu cuối
