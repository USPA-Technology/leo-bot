# Tìm hiểu `geo_places_pipeline`

Tài liệu này giải thích pipeline trong
[`geo_places_pipeline.py`](./geo_places_pipeline.py) theo hướng dành cho sinh
viên: pipeline làm gì, các bước phụ thuộc nhau ra sao, dữ liệu đi qua những
đâu và cách thử chạy.

## Mục tiêu

Pipeline tìm địa điểm quanh một vị trí, thu thập thêm thông tin từ web, rồi
lưu địa điểm và nội dung đã xử lý vào PostgreSQL. Ví dụ địa điểm có thể là nhà
hàng, nhà thờ hoặc một loại địa điểm khác.

Trong Dagster, các bước chính là **asset**. Có thể hình dung chúng như các
chặng tạo hoặc cập nhật dữ liệu bền vững:

```text
process_places
├── process_brave_search ───┐
└── process_mass_schedule ──┴──> process_knowledge
```

`process_brave_search` và `process_mass_schedule` có thể bắt đầu sau khi
`process_places` hoàn tất. `process_knowledge` đợi cả hai nhánh. Mũi tên ở đây
thể hiện **phụ thuộc của workflow**: asset ở trước cần được materialize trước
asset ở sau. Đây là DAG điều phối công việc, không phải khẳng định khoa học
rằng một địa điểm gây ra kết quả tìm kiếm trên web.

Một điểm đáng chú ý khi đọc code: các asset sau không nhận kết quả địa điểm
trực tiếp từ tham số của asset trước. Chúng truy vấn PostgreSQL để tìm các
địa điểm cần xử lý; Dagster theo dõi thứ tự thông qua `deps=[...]`.

## Bốn asset làm gì?

### 1. `process_places`: khám phá và lưu địa điểm

Asset này nhận `name`, `latitude`, `longitude`, `radius` và số kết quả `count`
từ run config. `GeoPlaceSearchService` gọi `BravePlaceSearchClient`, chuẩn hóa
kết quả thành các `BravePlace`, loại kết quả sai hoặc không phù hợp với từ
khóa, rồi loại trùng theo `geo_place_id`. `GeoPlaceRepository` dùng câu SQL
upsert để thêm hoặc cập nhật các hàng trong `geo_places`.

`BravePlace.from_search_result` là bước chuyển đổi dữ liệu từ API sang dạng
nội bộ. Nó đọc tên, tọa độ, địa chỉ, website, đánh giá và danh mục; tạo ID có
tiền tố như `brave_api:`; và tạo ID ổn định từ dữ liệu địa điểm khi kết quả
không có ID. Tọa độ có thể chưa có ở bước này; nhánh Brave Search có cơ hội
tìm lại chúng sau đó.

Vùng bán kính là tham số định hướng kết quả tìm kiếm, không phải cam kết rằng
mọi địa điểm được trả về đều nằm trong một đường tròn chính xác.

### 2. `process_brave_search`: tìm nguồn thông tin trên web

Asset chọn các địa điểm đến hạn cập nhật (mặc định sau 90 ngày), tạo truy vấn
từ tên, địa chỉ và danh mục, rồi tìm kết quả web có liên quan đến địa điểm.
Nếu địa điểm thiếu tọa độ, nó thử tìm lại tọa độ trước khi tiếp tục.

Với mỗi kết quả phù hợp, `BraveSearchRepository` lưu một nguồn vào
`knowledge_sources`, tạo embedding cho các đoạn trích (snippets), rồi lưu các
đoạn và vector vào `knowledge_chunks`. Đoạn không liên quan đến địa điểm sẽ
được bỏ qua. Mỗi địa điểm được ghi xuống cơ sở dữ liệu riêng trước khi chuyển
sang địa điểm kế tiếp.

### 3. `process_mass_schedule`: tìm giờ lễ cho nhà thờ

Nhánh này chuyên xử lý nhà thờ. `MassScheduleEnricher` lấy website của nhà
thờ, tải nội dung trang bằng `PublicWebPageFetcher`, rồi chỉ xét các liên kết
cùng website gốc (same origin) có dấu hiệu liên quan đến lịch lễ. Số trang
phụ được giới hạn bởi cấu hình.

`AIClient` đề xuất lịch theo cấu trúc JSON, nhưng code không lưu câu trả lời
một cách mù quáng: `_normalize_mass_item` kiểm tra ngày, định dạng giờ và
bằng chứng trích dẫn có thực sự xuất hiện trong nội dung trang hay không.
Lịch đạt kiểm tra được ghi vào `geo_places`. Địa điểm không phải nhà thờ được
bỏ qua trong một lượt chạy có phạm vi tìm kiếm dành riêng cho một danh mục
không liên quan.

### 4. `process_knowledge`: tạo nội dung để tra cứu

Asset này kết hợp dữ liệu địa điểm với thông tin đã tìm được. `PlaceEnricher`
yêu cầu `AIClient` tạo mô tả và thẻ ngắn chỉ dựa trên dữ liệu được cung cấp,
sau đó chia văn bản thành các đoạn nhỏ và tạo embedding cho từng đoạn.
`KnowledgeRepository` cập nhật mô tả/thẻ trong `geo_places`, lưu nguồn vào
`knowledge_sources`, rồi lưu các đoạn và vector vào `knowledge_chunks`.

Các embedding trong pipeline được kiểm tra là vector có 768 số hữu hạn trước
khi ghi vào cơ sở dữ liệu. Mỗi địa điểm được xử lý và commit riêng; nếu một
địa điểm lỗi, các địa điểm đã commit trước đó vẫn được giữ lại.

## Những lớp hỗ trợ trong file

- `PostgresResource` mở kết nối bằng DSN. Khi khối kết nối kết thúc thành
  công, nó commit; nếu có exception, nó rollback rồi ném lỗi tiếp.
- `BraveSearchResource` tạo client tìm địa điểm và client tìm nội dung web.
- `AIResource` tạo `AIClient` dùng chung cho tác vụ tạo JSON và embedding.
- Các lớp `...Config` mô tả cấu hình theo từng asset, thay vì đặt mọi tham số
  vào một cấu hình chung.
- Các lớp `...Repository` tập trung vào đọc/ghi PostgreSQL; các lớp
  `...Service` hoặc `...Enricher` tập trung vào gọi dịch vụ và xử lý dữ liệu.

Asset trả về `MaterializeResult` kèm metadata như số địa điểm đã thêm, nguồn
đã lưu, số đoạn kiến thức hoặc số lịch tìm thấy. Trong Dagster UI, các
metadata này giúp xem nhanh kết quả materialization mà không cần đọc toàn bộ
log.

## Cấu hình đầu vào

Khi materialize job `geo_places_pipeline`, `process_places` cần một lượt tìm
kiếm ban đầu. Ví dụ run config:

```yaml
ops:
  process_places:
    config:
      name: "church"
      latitude: 10.7536097
      longitude: 106.6284595
      radius: 6000
      count: 3
```

`count` có mặc định là 20 nếu không truyền. Các asset enrichment có cấu hình
riêng và giá trị mặc định:

| Cấu hình | Một số mặc định | Ý nghĩa |
| --- | --- | --- |
| `BraveSearchConfig` | `refresh_days=90`, `count=10`, `search_lang="vi"` | Ngưỡng làm mới, số kết quả và ngôn ngữ tìm kiếm |
| `MassScheduleConfig` | `refresh_days=60`, `min_confidence=0.6`, `max_subpages=3` | Ngưỡng làm mới, độ tin cậy tối thiểu và số trang phụ tối đa |
| `KnowledgeEnrichmentConfig` | 200 token mỗi đoạn, chồng lấp 40 token | Kích thước đoạn văn bản trước khi tạo embedding |

Các lớp cấu hình này cũng hỗ trợ giới hạn một lượt chạy vào một tìm kiếm cụ
thể bằng tên, tâm tọa độ, bán kính và tối đa năm địa điểm.

## Chạy thử và điều kiện cần

1. Cấu hình biến môi trường `PGSQL_DB_URL` để pipeline kết nối PostgreSQL.
2. Khởi tạo schema phát triển từ
   [`../sql_scripts/leo360_schema.sql`](../sql_scripts/leo360_schema.sql).
   Pipeline này không tự chạy migration.
3. Cấu hình thông tin truy cập cần thiết cho các client Brave và AI trong môi
   trường chạy.
4. Trong Dagster UI, chọn job `geo_places_pipeline`, nhập run config cho
   `process_places` như ví dụ trên và materialize job.

File cũng định nghĩa schedule `geo_places_full_refresh_weekly`, chạy lúc 02:00
mỗi Chủ nhật theo múi giờ của Dagster deployment. Cần bật schedule trong
Dagster nếu muốn nó tự chạy.

Có thể xem các ví dụ kiểm thử cho việc chuẩn hóa địa điểm, loại kết quả không
liên quan, cấu hình và xử lý enrichment trong
[`test_geo_places_pipeline.py`](../tests/test_geo_places_pipeline.py).

## Những điều cần nhớ khi học

- Thứ tự DAG cho biết asset nào phải hoàn thành trước; dữ liệu thực tế được
  chia sẻ qua PostgreSQL.
- API web và mô hình AI có thể trả dữ liệu thiếu hoặc lỗi. Pipeline kiểm tra
  dữ liệu đầu ra và ghi log thay vì giả định mọi câu trả lời đều hợp lệ.
- Các nhánh xử lý ghi dữ liệu theo từng địa điểm. Vì vậy, một lượt chạy thất
  bại không nhất thiết xóa các địa điểm đã xử lý thành công trước đó.
- Mô tả và lịch do AI hỗ trợ vẫn cần nguồn dữ liệu phù hợp; đặc biệt, lịch lễ
  phải có bằng chứng trong trang web mới được chấp nhận.
