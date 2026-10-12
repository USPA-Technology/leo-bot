# DAG bán hàng đơn giản: `causal_sales_dag`

Tài liệu này giải thích ví dụ DAG bán hàng trong
[`causal_sales_dag.py`](./causal_sales_dag.py). Mục tiêu là giúp bạn hiểu cách
các biến và giả định nhân quả được biểu diễn thành các bước chạy trong
Dagster.

Module chỉ định nghĩa job **`causal_sales_dag`**, với config, op và `defs`
riêng. Nó không import hay phụ thuộc vào mô hình geo marketing. Package
Dagster đăng ký job này độc lập với
[`geo_marketing_sales_dag`](./causal_geo_marketing_dag.md) qua
[`__init__.py`](./__init__.py).

Ví dụ đơn giản này chỉ mô tả funnel website, không có catchment, O2O,
công suất cửa hàng hay economics. Xem tài liệu geo marketing nếu cần
những nhánh đó. Tên job, khóa cấu hình và phương trình bên dưới giữ nguyên.

## DAG này mô tả điều gì?

Ví dụ giả định rằng chi tiêu quảng cáo, tính mùa vụ và chất lượng sản phẩm có
thể ảnh hưởng đến lượt hiển thị quảng cáo, lượt truy cập website và số giao
dịch mua hàng:

```text
marketing_spend ──> ad_impressions ──> website_visits ──> purchases
seasonality_index ───────────────────> website_visits
seasonality_index ─────────────────────────────────────> purchases
product_quality_index ─────────────────────────────────> purchases
```

Mũi tên `A -> B` biểu thị giả định rằng `A` là một nguyên nhân trực tiếp của
`B` trong mô hình. Ví dụ, `website_visits` có hai biến cha:
`ad_impressions` và `seasonality_index`. `purchases` có ba biến cha:
`website_visits`, `seasonality_index` và `product_quality_index`.

Trong code, DAG không được tạo bằng một thư viện vẽ đồ thị riêng. Dagster suy
ra các cạnh từ những giá trị được truyền giữa các op. Chẳng hạn,
`website_visits(impressions, seasonality)` tạo phụ thuộc từ hai op tạo ra
`impressions` và `seasonality` đến op `website_visits`.

## Biến đầu vào và cấu hình

Ba op gốc nhận giá trị từ cấu hình của lần chạy Dagster:

| Op | Ý nghĩa | Giá trị mặc định | Giới hạn |
| --- | --- | ---: | --- |
| `marketing_spend` | Chi tiêu quảng cáo, tính bằng nghìn USD | 10 | Không âm |
| `seasonality_index` | Mức độ mùa vụ | 0.5 | Từ 0 đến 1 |
| `product_quality_index` | Chỉ số chất lượng sản phẩm | 0.7 | Từ 0 đến 1 |

Các lớp `MarketingSpendConfig`, `SeasonalityConfig` và
`ProductQualityConfig` khai báo cấu hình cho từng op. `Field` đặt giá trị mặc
định và giới hạn hợp lệ. Đây là các biến đầu vào ngoại sinh trong ví dụ: mô
hình nhận chúng từ cấu hình thay vì tính chúng từ các biến khác trong DAG.

Bạn có thể thử các giá trị khác trong cấu hình của lần chạy:

```yaml
ops:
  marketing_spend:
    config:
      thousands_usd: 10
  seasonality_index:
    config:
      index: 0.5
  product_quality_index:
    config:
      index: 0.7
```

## Các phương trình cấu trúc

Mỗi op nhận các biến cha làm tham số và tính biến của chính nó. Các lượng
hiển thị ở đây được tính bằng nghìn:

1. **Lượt hiển thị quảng cáo**

   ```text
   ad_impressions = 100 * marketing_spend
   ```

   `marketing_spend` được tính bằng nghìn USD; kết quả là nghìn lượt hiển thị.
   Hệ số 100 là giả định minh họa của mô hình.

2. **Lượt truy cập website**

   ```text
   click_through_rate = 0.02 + 0.03 * seasonality_index
   website_visits = ad_impressions * click_through_rate
   ```

   Tỷ lệ nhấp cơ bản là 2%. Trong mô hình này, chỉ số mùa vụ làm tỷ lệ đó tăng
   tối đa thêm 3 điểm phần trăm.

3. **Số giao dịch mua hàng**

   ```text
   conversion_rate =
       0.02 + 0.03 * product_quality_index + 0.01 * seasonality_index
   purchases = website_visits * conversion_rate
   ```

   Tỷ lệ chuyển đổi cơ bản là 2%; chất lượng sản phẩm và mùa vụ góp thêm các
   phần được giả định trong công thức.

## Tính thử với giá trị mặc định

Với chi tiêu 10 nghìn USD, chỉ số mùa vụ 0.5 và chất lượng 0.7:

```text
ad_impressions = 100 * 10 = 1,000 nghìn lượt hiển thị
click_through_rate = 0.02 + 0.03 * 0.5 = 0.035 (3.5%)
website_visits = 1,000 * 0.035 = 35 nghìn lượt truy cập
conversion_rate = 0.02 + 0.03 * 0.7 + 0.01 * 0.5 = 0.046 (4.6%)
purchases = 35 * 0.046 = 1.61 nghìn giao dịch
```

Do đó, kết quả `purchases` mặc định là khoảng 1.61 nghìn giao dịch.

## Chạy riêng job bán hàng

Chọn `causal_sales_dag` trong Dagster Launchpad và dùng YAML ở trên, hoặc
chạy trong môi trường Python của dự án:

```python
from dags_pipelines.causal_sales_dag import causal_sales_dag

result = causal_sales_dag.execute_in_process()
print(result.output_for_node("purchases"))  # 1.61 nghìn giao dịch
```

`defs` của module này chỉ chứa job bán hàng; `defs` của module geo chỉ
chứa job geo. Có thể kiểm tra từng module riêng trước khi nạp code location
chung của package.

## Đọc log trong Dagster

Mỗi op dùng `context.log.info(...)` để ghi đầu vào, phương trình và kết quả
liên quan. `context` là `OpExecutionContext` do Dagster cung cấp; nó giúp op
ghi log gắn với đúng bước chạy. Sau khi chạy job, mở lần chạy trong Dagster UI
và xem tab **Logs** để theo dõi giá trị đi qua DAG, ví dụ:

```text
ad_impressions = 100 * 10.00 thousand USD = 1000.00 thousand impressions
website_visits = 1000.00 thousand impressions * (0.02 + 0.03 * 0.50 seasonality)
                 = 35.00 thousand visits (click-through rate: 3.5%)
purchases = 35.00 thousand visits * (0.02 + 0.03 * 0.70 quality + 0.01 * 0.50 seasonality)
            = 1.61 thousand purchases (conversion rate: 4.6%)
```

## Giới hạn của ví dụ

Đây là mô hình đồ chơi để học cấu trúc DAG và phương trình cấu trúc. Các hệ số
được chọn để minh họa, không được ước lượng từ dữ liệu. Vì vậy, các mũi tên
thể hiện giả định của mô hình chứ không chứng minh quan hệ nhân quả trong thế
giới thực. Ví dụ này cũng chưa mô hình hóa nhiễu, sai số, các yếu tố gây nhiễu
hay độ bất định.
