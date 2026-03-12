"""
PDF Parser - Extract transactions from bank statement PDFs
LiquidSuite/lsuite/gmail/parsers.py - COMPLETE FIXED VERSION
"""
import io
import os
import shutil
from pathlib import Path
import re
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class PDFParser:
    """PDF statement parser"""
    
    def parse_pdf(self, pdf_data, bank_name, password=None):
        """
        Parse PDF and extract transactions
        
        Args:
            pdf_data: Binary PDF data
            bank_name: Bank identifier (tymebank, capitec, other)
            password: PDF password if protected
            
        Returns:
            List of transaction dictionaries
        """
        text = self._extract_text_from_pdf(pdf_data, password)
        
        # Log extracted text for debugging
        logger.info(f"Extracted text length: {len(text)} characters")
        logger.debug(f"First 500 chars: {text[:500]}")
        
        if bank_name == 'tymebank':
            return self._parse_tymebank(text)
        elif bank_name == 'capitec':
            return self._parse_capitec(text)
        else:
            return self._parse_generic(text)
    
    def _extract_text_from_pdf(self, pdf_data, password=None):
        """Extract text using pdfplumber (preferred) then PyPDF2 fallback."""
        try:
            import pdfplumber
            text = self._extract_with_pdfplumber(pdf_data, password)
            logger.info(f"Extracted {len(text)} chars using pdfplumber")
            return text
        except ImportError:
            pass

        try:
            import PyPDF2
            text = self._extract_with_pypdf2(pdf_data, password)
            logger.info(f"Extracted {len(text)} chars using PyPDF2")
            return text
        except ImportError:
            pass

        raise ImportError("No PDF library found. Install pdfplumber: pip install pdfplumber")

    def _extract_with_pdfplumber(self, pdf_data, password=None):
        import pdfplumber
        pages = []
        open_kwargs = {"password": password} if password else {}
        with pdfplumber.open(io.BytesIO(pdf_data), **open_kwargs) as pdf:
            for page in pdf.pages:
                # Tight tolerances keep all columns on one line without merging rows
                txt = page.extract_text(x_tolerance=1, y_tolerance=1)
                if txt:
                    pages.append(txt)
        return '\n'.join(pages)

    def _extract_with_pypdf2(self, pdf_data, password=None):
        import PyPDF2
        pdf_reader = PyPDF2.PdfReader(io.BytesIO(pdf_data))
        if pdf_reader.is_encrypted:
            if not password:
                raise ValueError("PDF is password protected but no password provided")
            if pdf_reader.decrypt(password) == 0:
                raise ValueError("Incorrect PDF password")
        return '\n'.join(page.extract_text() or '' for page in pdf_reader.pages)
    
    def _parse_tymebank(self, text):
        """Parse TymeBank PDF format - FIXED VERSION
        
        TymeBank format:
        Date Description Fees Money Out Money In Balance
        04 Sep 2025 EFT for CAPITEC S SEANEGO - - 250.00 250.05
        
        Multi-line format:
        10 Sep 2025 Purchase at Boxer Spr Mabopane
        525309988959
        - 512.46 - 417.59
        """
        transactions = []
        
        # Split text into lines for processing
        lines = text.split('\n')
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            
            # Look for lines starting with a date pattern
            date_match = re.match(r'^(\d{1,2}\s+\w{3}\s+\d{4})\s+(.+)', line)
            
            if date_match:
                try:
                    date_str = date_match.group(1)
                    rest_of_line = date_match.group(2).strip()
                    
                    # Parse the date
                    trans_date = datetime.strptime(date_str, '%d %b %Y').date()
                    
                    # Build description starting with rest of first line
                    description_parts = [rest_of_line]
                    
                    # Look ahead for continuation lines and amounts
                    j = i + 1
                    amounts_found = False
                    fees = money_out = money_in = balance = None
                    
                    # Check next few lines (max 5 lines ahead for multi-line transactions)
                    while j < len(lines) and j < i + 6:
                        next_line = lines[j].strip()
                        
                        # Stop if we hit another date (start of next transaction)
                        if re.match(r'^\d{1,2}\s+\w{3}\s+\d{4}', next_line):
                            break
                        
                        # Better pattern that validates amounts are actually monetary values
                        amount_pattern = r'^(-|(?:\d{1,3}(?:,\d{3})*|\d+)(?:\.\d{2})?)\s+(-|(?:\d{1,3}(?:,\d{3})*|\d+)(?:\.\d{2})?)\s+(-|(?:\d{1,3}(?:,\d{3})*|\d+)(?:\.\d{2})?)\s+((?:\d{1,3}(?:,\d{3})*|\d+)(?:\.\d{2})?)\s*$'
                        amount_match = re.match(amount_pattern, next_line)
                        
                        if amount_match:
                            # Found the amounts line
                            fees = amount_match.group(1).strip()
                            money_out = amount_match.group(2).strip()
                            money_in = amount_match.group(3).strip()
                            balance = amount_match.group(4).strip()
                            amounts_found = True
                            i = j  # Move main counter to this position
                            break
                        else:
                            # Check if amounts are at the end of this line
                            inline_pattern = r'(.+?)\s+(-|(?:\d{1,3}(?:,\d{3})*|\d+)(?:\.\d{2})?)\s+(-|(?:\d{1,3}(?:,\d{3})*|\d+)(?:\.\d{2})?)\s+(-|(?:\d{1,3}(?:,\d{3})*|\d+)(?:\.\d{2})?)\s+((?:\d{1,3}(?:,\d{3})*|\d+)(?:\.\d{2})?)\s*$'
                            inline_amount_match = re.search(inline_pattern, next_line)
                            
                            if inline_amount_match:
                                # Description continues and amounts are on same line
                                description_parts.append(inline_amount_match.group(1).strip())
                                fees = inline_amount_match.group(2).strip()
                                money_out = inline_amount_match.group(3).strip()
                                money_in = inline_amount_match.group(4).strip()
                                balance = inline_amount_match.group(5).strip()
                                amounts_found = True
                                i = j
                                break
                            else:
                                # Only add to description if it's not a random number
                                # Skip lines that are just long numbers (like card numbers: 525309988959)
                                if next_line and not re.match(r'^\d{10,}$', next_line):
                                    # Check if it's a valid description line
                                    if len(next_line) > 0 and not next_line.startswith('-'):
                                        description_parts.append(next_line)
                        
                        j += 1
                    
                    # Try to find amounts on the same line as date if not found yet
                    if not amounts_found:
                        same_line_pattern = r'(.+?)\s+(-|(?:\d{1,3}(?:,\d{3})*|\d+)(?:\.\d{2})?)\s+(-|(?:\d{1,3}(?:,\d{3})*|\d+)(?:\.\d{2})?)\s+(-|(?:\d{1,3}(?:,\d{3})*|\d+)(?:\.\d{2})?)\s+((?:\d{1,3}(?:,\d{3})*|\d+)(?:\.\d{2})?)\s*$'
                        same_line_match = re.search(same_line_pattern, rest_of_line)
                        
                        if same_line_match:
                            description_parts = [same_line_match.group(1).strip()]
                            fees = same_line_match.group(2).strip()
                            money_out = same_line_match.group(3).strip()
                            money_in = same_line_match.group(4).strip()
                            balance = same_line_match.group(5).strip()
                            amounts_found = True
                    
                    # Process the transaction if amounts were found
                    if amounts_found:
                        # Build full description
                        description = ' '.join(description_parts)
                        description = ' '.join(description.split())  # Clean whitespace
                        
                        # Skip if description is too short or looks like a header
                        if len(description) < 3 or 'Description' in description or 'Money Out' in description:
                            i += 1
                            continue
                        
                        # Parse amounts with validation
                        def parse_amount_safe(amount_str):
                            """Safely parse amount with validation"""
                            if not amount_str or amount_str == '-':
                                return 0
                            try:
                                # Remove commas and spaces
                                cleaned = amount_str.replace(',', '').replace(' ', '').strip()
                                # Ensure it's not too large (max 10 million for a single transaction)
                                val = float(cleaned)
                                if val > 10_000_000:  # 10 million limit
                                    logger.warning(f"Amount too large, likely parsing error: {val} from '{amount_str}'")
                                    return 0
                                return val
                            except (ValueError, AttributeError):
                                logger.warning(f"Could not parse amount: '{amount_str}'")
                                return 0
                        
                        # Determine transaction type and amount
                        amount = 0
                        trans_type = 'debit'
                        
                        # Check Money In first (credits)
                        money_in_val = parse_amount_safe(money_in)
                        if money_in_val > 0:
                            amount = money_in_val
                            trans_type = 'credit'
                        
                        # Then check Money Out (debits)
                        money_out_val = parse_amount_safe(money_out)
                        if amount == 0 and money_out_val > 0:
                            amount = money_out_val
                            trans_type = 'debit'
                        
                        # Then check Fees (also debits)
                        fees_val = parse_amount_safe(fees)
                        if amount == 0 and fees_val > 0:
                            amount = fees_val
                            trans_type = 'debit'
                            description = f"{description} (Fee)"
                        
                        # Only add if we have a valid amount
                        if amount > 0:
                            transactions.append({
                                'date': trans_date,
                                'description': description,
                                'amount': amount,
                                'type': trans_type,
                                'reference': f"TYME-{trans_date.strftime('%Y%m%d')}-{len(transactions)}"
                            })
                            logger.debug(f"Parsed transaction: {description[:30]} = {amount}")
                        else:
                            logger.debug(f"Skipped transaction with zero amount: {description[:30]}")
                    
                except (ValueError, IndexError) as e:
                    logger.warning(f"Failed to parse TymeBank transaction: {e}")
            
            i += 1
        
        if not transactions:
            logger.warning("No transactions found with TymeBank pattern")
            logger.debug(f"Text sample for debugging:\n{text[:1000]}")
        else:
            logger.info(f"Successfully parsed {len(transactions)} TymeBank transactions")
        
        return transactions
    
    def _parse_capitec(self, text):
        """Parse Capitec statement text (layout-extracted or plain text).

        Capitec columns: Date | Description | Category | Money In | Money Out | Fee* | Balance
        Amounts use space-separated thousands: 3 465.00 or 1 030.73
        """
        transactions = []

        CATEGORIES = [
            'Investment Income', 'Other Income', 'Cash Withdrawal', 'Digital Payments',
            'Furniture & Appliances', 'Other Personal & Family', 'Card Subscriptions',
            'Debit Orders', 'Online Store',
            'Transfer', 'Savings', 'Investments', 'Fees', 'Interest', 'Groceries',
            'Cellphone', 'Uncategorised', 'Takeaways', 'Alcohol',
        ]
        CREDIT_KW = ['payment received', 'received', 'deposit', 'interest received',
                     'transfer received', 'refund']
        DEBIT_KW  = ['payment:', 'sent', 'cash sent', 'withdrawal', 'purchase',
                     'transfer to', 'prepaid', 'voucher', 'debicheck', 'insufficient funds']

        AMT = r'-?(?:0|[1-9]\d{0,2})(?:[, ]\d{3})*(?:\.\d{2})?\*?'

        def parse_amt(s):
            if not s:
                return 0.0
            try:
                return float(re.sub(r'[, \*]', '', s).strip())
            except ValueError:
                return 0.0

        def strip_amts_right(s, max_amts=3):
            """Peel up to max_amts amount tokens from the right. Returns (text, [amt_strs])."""
            amts = []
            while len(amts) < max_amts:
                m = re.search(rf'(?<![.\d])({AMT})\s*$', s)
                if not m:
                    break
                amts.insert(0, m.group(1))
                s = s[:m.start()].rstrip()
            return s, amts

        def extract_category(text_block):
            text_block = text_block.strip()
            for cat in CATEGORIES:
                if text_block == cat:
                    return cat, ''
                if text_block.endswith(' ' + cat):
                    return cat, text_block[:-len(cat)-1].rstrip()
            return 'Uncategorised', text_block

        def append_txn(trans_date, description, category, amounts):
            if len(amounts) == 3:
                trans, fee, balance = parse_amt(amounts[0]), parse_amt(amounts[1]), parse_amt(amounts[2])
            elif len(amounts) == 2:
                trans, fee, balance = parse_amt(amounts[0]), 0.0, parse_amt(amounts[1])
            elif len(amounts) == 1:
                trans, fee, balance = parse_amt(amounts[0]), 0.0, 0.0
            else:
                return

            description = description.strip()
            if abs(trans) == 0 or len(description) < 3:
                return

            # Amount sign is authoritative: negative = debit, positive = credit
            if trans < 0:
                t_type = 'debit'
            elif trans > 0:
                t_type = 'credit'
            else:
                # Zero or ambiguous — fall back to keywords
                desc_lower = description.lower()
                if any(k in desc_lower for k in CREDIT_KW) or 'income' in category.lower():
                    t_type = 'credit'
                else:
                    t_type = 'debit'

            transactions.append({
                'date': trans_date,
                'description': description,
                'amount': abs(trans),
                'type': t_type,
                'reference': f"CAP-{trans_date.strftime('%Y%m%d')}-{len(transactions)}",
                'category': category,
                'fee': abs(fee),
                'balance': balance,
            })
            logger.debug(f"Capitec: {description[:45]} = {abs(trans)} ({t_type})")

        lines = text.split('\n')
        i = 0
        while i < len(lines):
            line = lines[i].strip()

            skip_phrases = ('Transaction History', '* Includes VAT', '24hr Client',
                            'Capitec Bank is', 'Unique Document', 'Date Description',
                            'Spending Summary', 'Scheduled Payments', 'Debit Orders',
                            'Card Subscriptions', 'Money In Summary', 'Money Out Summary',
                            'Fee Summary', 'Live Better')
            if not line or any(p in line for p in skip_phrases):
                i += 1
                continue

            # Skip lines with -R prefix amounts (summary sections, not transaction history)
            if re.search(r'-R\d', line):
                i += 1
                continue

            date_m = re.match(r'^(\d{2}/\d{2}/\d{4})\s+(.+)', line)
            if not date_m:
                i += 1
                continue

            try:
                trans_date = datetime.strptime(date_m.group(1), '%d/%m/%Y').date()
                rest = date_m.group(2).strip()

                desc_cat, amounts = strip_amts_right(rest)

                if amounts:
                    # Extract category BEFORE absorbing any continuation (ref numbers etc.)
                    cat, desc = extract_category(desc_cat)
                    append_txn(trans_date, desc, cat, amounts)

                else:
                    # No amounts on date line — scan up to 6 lines ahead
                    j = i + 1
                    extra = []
                    found = False
                    while j < len(lines) and j < i + 7:
                        nxt = lines[j].strip()
                        if not nxt:
                            j += 1
                            continue
                        if re.match(r'\d{2}/\d{2}/\d{4}', nxt):
                            break
                        nxt_text, nxt_amts = strip_amts_right(nxt)
                        if nxt_amts:
                            full = ' '.join(filter(None, [rest] + extra + ([nxt_text] if nxt_text else [])))
                            cat, desc = extract_category(full)
                            append_txn(trans_date, desc, cat, nxt_amts)
                            i = j
                            found = True
                            break
                        extra.append(nxt)
                        j += 1

            except (ValueError, IndexError) as e:
                logger.warning(f"Capitec parse error: {e} — {line}")

            i += 1

        if not transactions:
            logger.warning("No Capitec transactions found")
            logger.debug(f"Text sample:\n{text[:500]}")
        else:
            logger.info(f"Parsed {len(transactions)} Capitec transactions")

        return transactions

    def _parse_generic(self, text):
        """Generic PDF parsing for unknown banks"""
        transactions = []
        
        # Generic patterns that might work for various banks
        patterns = [
            (r'(\d{2}/\d{2}/\d{4})\s*[|\|]\s*([^|\|]+?)\s*[|\|]\s*(-?R?[\d,]+\.\d{2})', '%d/%m/%Y'),
            (r'(\d{2}/\d{2}/\d{4})\s+([^\d\-\+\$R]+?)\s+(-?R?[\d,]+\.\d{2})', '%d/%m/%Y'),
            (r'(\d{4}-\d{2}-\d{2})\s+([^\d\-\+\$R]+?)\s+(-?R?[\d,]+\.\d{2})', '%Y-%m-%d'),
            (r'(\d{2}\s+\w{3}\s+\d{4})\s+([^\d\-\+\$R]+?)\s+(-?R?[\d,]+\.\d{2})', '%d %b %Y'),
        ]
        
        for pattern, date_format in patterns:
            matches = re.findall(pattern, text, re.MULTILINE)
            
            if matches:
                logger.info(f"Found {len(matches)} transactions with generic pattern")
                
                for match in matches:
                    try:
                        trans_date = datetime.strptime(match[0].strip(), date_format).date()
                        description = match[1].strip()
                        amount_str = match[2].replace('R', '').replace('$', '').replace(',', '').strip()
                        amount = float(amount_str)
                        
                        # Skip if description is too short
                        if len(description) < 3:
                            continue
                        
                        transactions.append({
                            'date': trans_date,
                            'description': description,
                            'amount': abs(amount),
                            'type': 'debit' if amount < 0 else 'credit',
                            'reference': f"GEN-{trans_date.strftime('%Y%m%d')}-{len(transactions)}"
                        })
                        
                    except (ValueError, IndexError) as e:
                        logger.warning(f"Failed to parse generic transaction: {e}")
                        continue
                
                if transactions:
                    break
        
        return transactions
    
    def parse_html_email(self, html_content, bank_name):
        """Parse transaction table from HTML email"""
        from bs4 import BeautifulSoup
        
        transactions = []
        
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            tables = soup.find_all('table')
            
            for table in tables:
                rows = table.find_all('tr')
                
                # Skip header row
                for row in rows[1:]:
                    cols = row.find_all('td')
                    
                    if len(cols) >= 3:
                        try:
                            date_text = cols[0].get_text().strip()
                            description = cols[1].get_text().strip()
                            amount_text = cols[2].get_text().strip()
                            
                            # Parse date
                            trans_date = None
                            for date_fmt in ['%d/%m/%Y', '%Y-%m-%d', '%d %b %Y']:
                                try:
                                    trans_date = datetime.strptime(date_text, date_fmt).date()
                                    break
                                except ValueError:
                                    continue
                            
                            if not trans_date:
                                continue
                            
                            # Parse amount
                            amount_str = re.sub(r'[^\d\.\-]', '', amount_text)
                            amount = float(amount_str)
                            
                            transactions.append({
                                'date': trans_date,
                                'description': description,
                                'amount': abs(amount),
                                'type': 'debit' if amount < 0 else 'credit',
                                'reference': f"HTML-{trans_date.strftime('%Y%m%d')}"
                            })
                            
                        except (ValueError, IndexError):
                            continue
            
            logger.info(f"Extracted {len(transactions)} transactions from HTML email")
            
        except Exception as e:
            logger.error(f"HTML parsing error: {e}")
        
        return transactions

if __name__ == "__main__":
    path = str(os.getcwd()).replace('\\','/')
    pdf = f"{path}/data/account_statement-1_032727.pdf"
    parser = PDFParser()
    #print(pdf,type(Path(pdf).read_bytes()))
    parsed_pdf = parser.parse_pdf(Path(pdf).read_bytes(),'capitec')
    transactions = {}
    for trans in parsed_pdf:
        #for key, items in parsed_pdf[0].items():
            if not trans['date'] in transactions.keys():
                transactions[trans['date']] = [trans]
            else:
                transactions[trans['date']].append(trans)
            #print(transactions[trans['date']],'\n\n\n')
