import os
from datetime import date

import boto3


def _region() -> str:
    return (
        os.getenv("AWS_REGION")
        or os.getenv("AWS_DEFAULT_REGION")
        or boto3.session.Session().region_name
    )


def _get_ssm_parameter(name: str) -> str:
    ssm = boto3.client("ssm", region_name=_region())
    return ssm.get_parameter(Name=name, WithDecryption=False)["Parameter"]["Value"]


def main() -> None:
    table_name = _get_ssm_parameter("/app/customersupport/dynamodb/warranty_table_name")
    dynamodb = boto3.resource("dynamodb", region_name=_region())
    table = dynamodb.Table(table_name)

    today = date.today()

    items = [
        {
            "serial_number": "MNO33333333",
            "customer_id": "CUST001",
            "product_name": "Gaming Console Pro",
            "purchase_date": str(today.replace(year=today.year - 1)),
            "warranty_end_date": str(today.replace(year=today.year + 1)),
            "warranty_type": "Standard",
            "customer_name": "Alex Morgan",
            "coverage_details": "Includes hardware defects and standard support",
        },
        {
            "serial_number": "ABC98765432",
            "customer_id": "CUST002",
            "product_name": "ThinkPad X1 Carbon",
            "purchase_date": str(today.replace(year=today.year - 2)),
            "warranty_end_date": str(today.replace(year=today.year + 1)),
            "warranty_type": "Extended",
            "customer_name": "Jamie Lee",
            "coverage_details": "Covers hardware defects, battery, and accidental damage",
        },
        {
            "serial_number": "XYZ11112222",
            "customer_id": "CUST003",
            "product_name": "NoiseCancel Headphones",
            "purchase_date": str(today.replace(year=today.year - 1)),
            "warranty_end_date": str(today.replace(year=today.year, month=today.month, day=today.day)),
            "warranty_type": "Standard",
            "customer_name": "Taylor Reed",
            "coverage_details": "Includes manufacturing defects",
        },
    ]

    with table.batch_writer() as batch:
        for item in items:
            batch.put_item(Item=item)

    print(f"✅ Seeded {len(items)} warranty items into {table_name}")


if __name__ == "__main__":
    main()
