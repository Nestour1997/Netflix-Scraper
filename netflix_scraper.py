import asyncio
import re
import pandas as pd
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

# -------------------------------------
# Enhanced Price Extraction
# -------------------------------------
def extract_price_details(price_text):
    """
    Extract currency, amount, and note from price text that includes '/month'.
    """
    if not price_text or "month" not in price_text.lower():
        return "Unknown", "", price_text

    # Normalize the string
    text = price_text.strip()

    # Find the first occurrence of '/month' (or variants)
    month_split = re.split(r"/\s*month", text, flags=re.IGNORECASE)
    price_part = month_split[0].strip()
    note_part = month_split[1].strip() if len(month_split) > 1 else ""

    # Extract amount and currency from the price_part
    number_match = re.search(r"([\d,.]+)", price_part)
    currency_match = re.search(r"([^\d\s,.]+)", price_part)

    amount = number_match.group(1).replace(",", "") if number_match else ""
    currency = currency_match.group(1) if currency_match else "Unknown"

    return currency, amount, note_part


# -------------------------------------
# Country processing
# -------------------------------------
async def process_country(country, page):
    results = []

    try:
        await page.goto("https://help.netflix.com/en/node/24926", timeout=60000)
        await page.wait_for_timeout(2000)

        # Accept cookies
        try:
            await page.click("#onetrust-accept-btn-handler", timeout=3000)
        except:
            pass

        # Open dropdown & select country
        await page.click("div.css-hlgwow", timeout=5000)
        input_box = await page.wait_for_selector('//input[@type="text"]')
        await input_box.fill("")
        await input_box.type(country)
        await input_box.press("Enter")
        await page.wait_for_timeout(3000)

        content = await page.content()
        soup = BeautifulSoup(content, "html.parser")
        pricing_header = soup.find("h3", string=lambda s: s and "Pricing" in s)

        if pricing_header:
            ul = pricing_header.find_next("ul")
            if ul:
                for li in ul.find_all("li"):
                    if ":" in li.text:
                        plan, price_text = li.text.strip().split(":", 1)
                        currency, amount, note = extract_price_details(price_text.strip())
                        results.append({
                            "Country": country,
                            "Plan": plan.strip(),
                            "Price": price_text.strip(),
                            "Currency": currency,
                            "Amount": amount,
                            "Note": note
                        })
        if not results:
            results.append({"Country": country, "Plan": "N/A", "Price": "N/A", "Currency": "", "Amount": "", "Note": ""})

        print(f"✅ {country}")
        return results

    except Exception as e:
        print(f"❌ Error: {country} — {e}")
        return [{"Country": country, "Plan": "ERROR", "Price": str(e), "Currency": "", "Amount": "", "Note": ""}]

# -------------------------------------
# Main function
# -------------------------------------
async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        # Fetch countries via JS
        await page.goto("https://help.netflix.com/en/node/24926")
        await page.wait_for_timeout(3000)
        try:
            await page.click("#onetrust-accept-btn-handler", timeout=3000)
        except:
            pass

        countries_data = await page.evaluate("window.netflix.data.article.allCountries")
        countries = [entry["label"] for entry in countries_data]
        await page.close()

        print(f"🌍 Found {len(countries)} countries")

        # Control how many tabs at once
        batch_size = 5
        results = []

        for i in range(0, len(countries), batch_size):
            tasks = []
            pages = []

            for country in countries[i:i+batch_size]:
                tab = await context.new_page()
                pages.append(tab)
                tasks.append(process_country(country, tab))

            batch_results = await asyncio.gather(*tasks)
            for res in batch_results:
                results.extend(res)

            for p in pages:
                await p.close()

        await browser.close()

        # Save
        df = pd.DataFrame(results)
        df.to_excel("netflix_pricing_by_country.xlsx", index=False, engine="openpyxl")
        print("✅ Saved to 'netflix_pricing_by_country.csv'")

# Run
if __name__ == "__main__":
    asyncio.run(main())
