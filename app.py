import streamlit as st
import pandas as pd
import random
import time
from datetime import datetime, timedelta
import asyncio
import aiohttp
from bs4 import BeautifulSoup
import re
from typing import List, Tuple
import pycountry

async def fetch_hotel_page(session: aiohttp.ClientSession, url: str) -> str:
    headers = {
        'User-Agent': 'Mozilla/5.0 (X11; CrOS x86_64 8172.45.0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/51.0.2704.64 Safari/537.36',
        'Accept-Language': 'en-US, en;q=0.5'
    }
    try:
        async with session.get(url, headers=headers) as response:
            response.raise_for_status()
            return await response.text()
    except Exception as e:
        print(f"Error fetching {url}: {str(e)}")
        return ""

async def get_hotel_details_async(session: aiohttp.ClientSession, hotel_url_name: str, 
                                 check_in_date: str, check_out_date: str, 
                                 country: str, currency: str) -> pd.DataFrame:
    url = f'https://www.booking.com/hotel/{country}/{hotel_url_name}.en-gb.html?checkin={check_in_date};checkout={check_out_date};dist=0;group_adults=2;group_children=0;selected_currency={currency}'
    
    html = await fetch_hotel_page(session, url)
    if not html:
        return pd.DataFrame()
    
    hotel_details = await parse_hotel_page(html, hotel_url_name, check_in_date, check_out_date, url)
    return hotel_details

def extract_room_area(row):
    try:
        # Find any element that likely contains area information
        area_elements = row.find_all(['span', 'div'], class_=lambda x: x and any(
            cls in str(x) for cls in ['bui-badge', 'room-size', 'facility', 'hprt-facility']
        ))
        
        # Search through all potential elements
        for element in area_elements:
            text = ' '.join(element.stripped_strings)  # Get all text with normalized whitespace
            
            # More comprehensive regex pattern (supports "ft²", "sq ft", "m²", "sqm", etc.)
            match = re.search(
                r'(\d+[.,]?\d*)\s*(?:square\s*)?(feet²|ft²|sq\s*ft|m²|sqm|sq\s*m|meters²)',
                text,
                re.IGNORECASE
            )
            
            if match:
                area_value = match.group(1).replace(',', '')  # Remove commas (e.g., "1,500" → "1500")
                unit = match.group(2).lower()  # Normalize unit to lowercase
                
                # Convert unit to a standard format (e.g., "sq ft" → "feet²", "sqm" → "m²")
                if unit in ['ft²', 'sq ft', 'sqft']:
                    unit = 'feet²'
                elif unit in ['m²', 'sqm', 'sq m']:
                    unit = 'm²'
                
                # Convert area_value to float or int
                area_value = float(area_value) if '.' in area_value else int(area_value)
                
                return (area_value, unit)
                
        return None  # No area found

    except Exception as e:
        print(f"Error extracting room area: {e}")
        return None
        
    except Exception as e:
        print(f"Error extracting room area: {e}")
        return None

async def parse_hotel_page(html: str, hotel_name: str, check_in_date: str, check_out_date: str, url: str) -> pd.DataFrame:
    soup = BeautifulSoup(html, 'html.parser')
    data = []
    
    # Extract hotel display name (more readable than URL name)
    display_name = soup.find('h2', {'class': 'hp__hotel-name'})
    hotel_display_name = display_name.get_text(strip=True) if display_name else hotel_name
    
    tables = soup.find_all('table', class_='hprt-table')
    for table in tables:
        for row in table.find_all('tr', {'data-block-id': True}):
            room_name = row.find('span', class_='hprt-roomtype-icon-link')
            room_name = room_name.get_text(strip=True) if room_name else None
            

            st.write(room_price)
            room_price = row.find('span', class_='prco-valign-middle-helper')
            room_price = re.sub(r'[^\d]', '', str(room_price)) if room_price else None
            

            if extract_room_area(row):
                area_unit, room_area = extract_room_area(row)
                
                data.append({
                    'hotel_name': hotel_display_name,
                    'check_in_date': check_in_date,
                    'check_out_date': check_out_date,
                    'room_name': room_name,
                    'room_price': room_price,
                    'room_area': room_area,
                    'area_unit': area_unit,  # Or modify extract_room_area() to return unit
                    'url': url
                })
    
    return pd.DataFrame(data)

async def gather_hotel_data(hotel_list: List[str], date_ranges: List[Tuple[str, str]], 
                          country: str, currency: str, max_concurrent: int = 10) -> pd.DataFrame:
    connector = aiohttp.TCPConnector(limit=max_concurrent)
    timeout = aiohttp.ClientTimeout(total=30)
    
    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        tasks = []
        for hotel_name in hotel_list:
            for date_range in date_ranges:
                task = get_hotel_details_async(session, hotel_name, date_range[0], date_range[1], country, currency)
                tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Handle exceptions and filter out empty DataFrames
        valid_dfs = []
        for result in results:
            if isinstance(result, Exception):
                print(f"Error in task: {str(result)}")
            elif not result.empty:
                valid_dfs.append(result)
        
        return pd.concat(valid_dfs, ignore_index=True) if valid_dfs else pd.DataFrame()

def main_async(hotel_list: List[str], date_ranges: List[Tuple[str, str]], 
         country: str = "sg", currency: str = "SGD") -> pd.DataFrame:
    return asyncio.run(gather_hotel_data(hotel_list, date_ranges, country, currency))

def generate_date_ranges(start_date, delta):
    if start_date:
        end_date = start_date + timedelta(days=delta)  # One year from start date
        
        date_ranges = []
        current_date = start_date
        while current_date < end_date:
            month_start = current_date.replace(day=1)
            next_month = month_start.replace(day=28) + timedelta(days=4)  # Move to next month
            month_end = next_month - timedelta(days=next_month.day)
            
            # Generate a random 8-day range within the month
            start_day = random.randint(1, max(1, month_end.day - 7))
            range_start = month_start.replace(day=start_day)
            range_end = range_start + timedelta(days=7)
            
            date_ranges.append((range_start.strftime("%Y-%m-%d"), range_end.strftime("%Y-%m-%d")))
            current_date = month_end + timedelta(days=1)
    return date_ranges

def country_currency_selectors():
    # Create columns for side-by-side layout
    col1, col2 = st.columns(2)
    
    with col1:
        # Country selector (returns 2-letter code)
        countries = [(country.name, country.alpha_2) for country in pycountry.countries]
        countries.sort()
        country_code = st.selectbox(
            "Select Country",
            countries,
            format_func=lambda x: x[0],
            index=countries.index(("United States", "US"))
        )[1]  # Get just the code
    
    with col2:
        # Currency selector
        currency = st.selectbox(
            "Select Currency",
            ["USD", "EUR", "SGD"],
            index=0  # Default to USD
        )
    
        return country_code, currency


    st.header("Dynamic String Input")
    
    if 'inputs' not in st.session_state:
        st.session_state.inputs = [""]  # Start with one empty field
    
    col1, col2 = st.columns([4, 1])
    
    # Display all current inputs
    for i in range(len(st.session_state.inputs)):
        st.session_state.inputs[i] = st.text_input(
            f"Item {i+1}", 
            st.session_state.inputs[i],
            key=f"input_{i}"
        )
    
    # Add/remove buttons
    with col1:
        if st.button("➕ Add another"):
            st.session_state.inputs.append("")
    
    with col2:
        if st.button("➖ Remove last") and len(st.session_state.inputs) > 1:
            st.session_state.inputs.pop()
    
    # Return non-empty strings
    return [item for item in st.session_state.inputs if item.strip()]

def multi_string_input(
    label: str = "Enter items",
    default_items: List[str] = None,
    key: str = "multi_string") -> List[str]:
    """
    A combined bulk/manual string input component.
    
    Args:
        label: Label to display above the component
        default_items: Pre-populate with these strings
        key: Unique key for session state
        
    Returns:
        List of non-empty strings entered by user
    """
    if default_items is None:
        default_items = [""]
    
    # Initialize session state
    if key not in st.session_state:
        st.session_state[key] = {
            "bulk": "\n".join(default_items),
            "manual": default_items.copy(),
            "active_tab": "bulk"
        }
    
    st.markdown(f"**{label}**")
    tab1, tab2 = st.tabs(["📋 Bulk Input", "✏️ Manual Entry"])
    
    with tab1:
        bulk_strings = st.text_area(
            "One item per line",
            st.session_state[key]["bulk"],
            key=f"{key}_bulk",
            height=150,
            label_visibility="collapsed"
        )
        st.session_state[key]["bulk"] = bulk_strings
    
    with tab2:
        cols = st.columns([4, 1])
        with cols[0]:
            if st.button("➕ Add hotel", key=f"{key}_add"):
                st.session_state[key]["manual"].append("")
        with cols[1]:
            if st.button("➖ Remove last", key=f"{key}_remove") and len(st.session_state[key]["manual"]) > 1:
                st.session_state[key]["manual"].pop()
        
        for i in range(len(st.session_state[key]["manual"])):
            st.session_state[key]["manual"][i] = st.text_input(
                f"Item {i+1}",
                st.session_state[key]["manual"][i],
                key=f"{key}_manual_{i}",
                label_visibility="collapsed"
            )
    
    # Determine which tab is active based on input
    if st.session_state[key]["bulk"].strip():
        active = "bulk"
        strings = [s.strip() for s in st.session_state[key]["bulk"].split('\n') if s.strip()]
    else:
        active = "manual"
        strings = [s.strip() for s in st.session_state[key]["manual"] if s.strip()]
    
    # Visual feedback about input mode
    st.caption(f"Using {active} input ({len(strings)} items)")
    
    return strings

def show_items_pretty(items, title="Current Items"):
    if not items:
        st.info("No items entered yet")
        return
    
    st.markdown(f"### {title}")
    container = st.container()
    
    for i, item in enumerate(items):
        container.markdown(f"""
        <div style="
            animation: fadeIn 0.5s;
            padding: 12px;
            margin: 8px 0;
            background: white;
            border-left: 4px solid #4a8bfc;
            border-radius: 0 8px 8px 0;
            box-shadow: 0 1px 2px rgba(0,0,0,0.1);
        ">
            <div style="display: flex;">
                <div style="color: #4a8bfc; margin-right: 10px;">▶</div>
                <div>{item}</div>
            </div>
        </div>
        
        <style>
            @keyframes fadeIn {{
                0% {{ opacity: 0; transform: translateX(-10px); }}
                100% {{ opacity: 1; transform: translateX(0); }}
            }}
        </style>
        """, unsafe_allow_html=True)

def multi_string_input_with_preview(label: str = "Enter items"):
    items = multi_string_input(label)
    
    # Display the pretty version
    if items:
        show_items_pretty(items, "Your Items")
        st.success(f"Total: {len(items)} items")
    else:
        st.info("No items added yet")
    
    return items


# Streamlit UI

st.set_page_config(
    page_title="Hotel Scraper",  # This changes the browser tab title
    page_icon="🏨",              # Optional: adds a favicon
    layout="wide"
)

st.title("Hotel Room Price Scrapping")

country, currency = country_currency_selectors()
st.write(f"Selected: {country} | {currency}")

hotel_list = multi_string_input("Enter hotel url names:")
hotel_list = list(map(lambda x: x.lower(), hotel_list))

st.write("Current items:", hotel_list)
# Date input for start date
start_date = st.date_input("Select a start date:")

if st.button("Process Data"):
    if hotel_list:
        result_df = main_async(hotel_list, generate_date_ranges(start_date, 365), country=country.lower(), currency=currency)
        if len(result_df) > 0:
            # 1. Remove rows where room_name is empty/NaN
            result_df = result_df.dropna(subset=['room_name'])

            # 2. For each date combination, keep only the cheapest version of each room
            result_df = (result_df
                        .sort_values('room_price')  # Sort by price to keep cheapest
                        .groupby(['check_in_date', 'check_out_date', 'room_name'], as_index=False)
                        .first()  # Takes the first (cheapest) occurrence
                        .sort_values(['check_in_date', 'room_price'])  # Final sorting
                        .reset_index(drop=True))

            # 3. Reorder columns to put hotel_name first
            column_order = ['hotel_name'] + [col for col in result_df.columns if col != 'hotel_name']
            result_df = result_df[column_order]

            # 4. Sort by check_in_date and hotel_name
            result_df = result_df.sort_values(['check_in_date', 'hotel_name'])

            # 5. Reset index for cleaner output
            result_df = result_df.reset_index(drop=True)

            st.dataframe(result_df)
        
        else:
            st.warning("Check country, currency or hotel name inputs")
    
    else:
        st.warning("Please enter at least one item")
