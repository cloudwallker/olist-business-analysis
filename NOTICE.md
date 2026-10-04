# Attribution and use conditions

Original project code and documentation: copyright 2026 cloudwallker. No separate reuse license has been selected for the original code. A public repository does not change the dataset's conditions.

The input is **Brazilian E-Commerce Public Dataset by Olist**, published by Olist: https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce. The official data card declares **CC BY-NC-SA 4.0**: https://creativecommons.org/licenses/by-nc-sa/4.0/.

The anonymous dashboard CSVs, cached dashboard data, aggregated results and analysis charts are adaptations: dates and amounts are typed; identical rows are deduplicated; order-level facts and metrics are derived; identifiers and review text are omitted from the public dashboard exports. These adapted data materials retain attribution and are distributed under **CC BY-NC-SA 4.0**, including its noncommercial and share-alike conditions. Raw source CSVs are not redistributed in this repository.

The JSON schemas under `dashboard/schemas` originate from Microsoft's official Fabric / Power BI schema endpoints and the Microsoft `json-schemas` repository: https://github.com/microsoft/json-schemas. Their MIT notice is retained in `dashboard/schemas/LICENSE`. Microsoft schemas retain their original license; their inclusion does not grant an MIT license to the Olist data.

Python packages, Power BI Desktop and locally downloaded development tools retain their own licenses. Tool installers and credentials are excluded from publication.
