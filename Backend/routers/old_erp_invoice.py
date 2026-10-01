from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from database import get_conn

router = APIRouter()

# ==========================================
# 1. FILTER DROPDOWN OPTIONS (distinct values)
# ==========================================
@router.get("/api/old_erp_invoice/filters")
def get_filter_options():
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("SELECT DISTINCT prod_category FROM old_erp_invoice_data WHERE prod_category IS NOT NULL ORDER BY prod_category ASC")
        categories = [r[0] for r in cur.fetchall()]

        cur.execute("SELECT DISTINCT inv_type FROM old_erp_invoice_data WHERE inv_type IS NOT NULL ORDER BY inv_type ASC")
        inv_types = [r[0] for r in cur.fetchall()]

        cur.execute("SELECT DISTINCT stock_type FROM old_erp_invoice_data WHERE stock_type IS NOT NULL ORDER BY stock_type ASC")
        stock_types = [r[0] for r in cur.fetchall()]

        return {
            "categories": categories,
            "inv_types": inv_types,
            "stock_types": stock_types
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()


# ==========================================
# 2. PAGINATED + FILTERED DATA (with summary)
# ==========================================
@router.get("/api/old_erp_invoice/data")
def get_invoice_data(
    page: int = Query(1, ge=1),
    page_size: int = Query(200, ge=1, le=1000),
    inv_from: Optional[str] = None,
    inv_to: Optional[str] = None,
    inv_no: Optional[str] = None,
    cust_code: Optional[str] = None,
    cust_name: Optional[str] = None,
    cust_city: Optional[str] = None,
    prod_code: Optional[str] = None,
    prod_desc: Optional[str] = None,
    prod_category: Optional[str] = None,
    inv_type: Optional[str] = None,
    stock_type: Optional[str] = None,
    unit_code: Optional[str] = None
):
    conn = get_conn()
    cur = conn.cursor()
    try:
        where_clauses = []
        params = []

        if inv_from:
            where_clauses.append("inv_date >= %s")
            params.append(inv_from)
        if inv_to:
            where_clauses.append("inv_date <= %s")
            params.append(inv_to)
        if inv_no:
            where_clauses.append("inv_no = %s")
            params.append(inv_no.strip())
        if cust_code:
            where_clauses.append("cust_code = %s")
            params.append(cust_code.strip())
        if cust_name:
            where_clauses.append("cust_name ILIKE %s")
            params.append(f"%{cust_name.strip()}%")
        if cust_city:
            where_clauses.append("cust_city_code ILIKE %s")
            params.append(f"%{cust_city.strip()}%")
        if prod_code:
            where_clauses.append("prod_code = %s")
            params.append(prod_code.strip())
        if prod_desc:
            where_clauses.append("product_desc ILIKE %s")
            params.append(f"%{prod_desc.strip()}%")
        if prod_category:
            where_clauses.append("prod_category = %s")
            params.append(prod_category)
        if inv_type:
            where_clauses.append("inv_type = %s")
            params.append(inv_type)
        if stock_type:
            where_clauses.append("stock_type = %s")
            params.append(stock_type)
        if unit_code:
            where_clauses.append("unit_code = %s")
            params.append(unit_code.strip())

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        # ---- Summary aggregate over the FULL filtered set ----
        summary_query = f"""
            SELECT 
                COUNT(*) as total_rows,
                COUNT(DISTINCT inv_no) as distinct_invoices,
                COALESCE(SUM(qty), 0) as total_qty,
                COALESCE(SUM(basic_amount), 0) as total_amount
            FROM old_erp_invoice_data
            {where_sql}
        """
        cur.execute(summary_query, tuple(params))
        total_rows, distinct_invoices, total_qty, total_amount = cur.fetchone()

        total_pages = max(1, (total_rows + page_size - 1) // page_size)
        offset = (page - 1) * page_size

        # ---- Paginated data ----
        data_query = f"""
            SELECT unit_code, cust_code, cust_name, cust_city_code, prod_category,
                   inv_no, inv_date, prod_code, product_desc, qty, basic_amount,
                   inv_type, stock_type
            FROM old_erp_invoice_data
            {where_sql}
            ORDER BY inv_date DESC, inv_no DESC
            LIMIT %s OFFSET %s
        """
        cur.execute(data_query, tuple(params) + (page_size, offset))
        rows = cur.fetchall()

        records = []
        for r in rows:
            records.append({
                "unit_code": r[0],
                "cust_code": r[1],
                "cust_name": r[2],
                "cust_city_code": r[3],
                "prod_category": r[4],
                "inv_no": r[5],
                "inv_date": str(r[6]) if r[6] else "",
                "prod_code": r[7],
                "product_desc": r[8],
                "qty": float(r[9]) if r[9] is not None else 0,
                "basic_amount": float(r[10]) if r[10] is not None else 0,
                "inv_type": r[11],
                "stock_type": r[12]
            })

        return {
            "records": records,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "total_rows": total_rows,
            "distinct_invoices": distinct_invoices,
            "total_qty": float(total_qty),
            "total_amount": float(total_amount)
        }
    except Exception as e:
        print(f"OLD ERP INVOICE DATA ERROR: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()