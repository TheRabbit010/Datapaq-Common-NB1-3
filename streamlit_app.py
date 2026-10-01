# ======================= FURNACE IDENTIFICATION =======================
    furnace_id, furnace_variant = "NB3", "NB3"
    
    # 1. ตรวจสอบ NB1 (RAD)
    if re.search(r'\bRAD\b', recipe_corpus, re.IGNORECASE): 
        furnace_id, furnace_variant = "NB1", "NB1 (RAD)"
    
    # 2. ตรวจสอบ NB2 (Tahc/Utahc) ตามรูปแบบชื่อไฟล์ภาพขวา (UT, G2, Tahc, Utahc, NB2)
    elif re.search(r'\b(Tahc|Utahc|UT|G2|NB2)\b', recipe_corpus, re.IGNORECASE): 
        furnace_id, furnace_variant = "NB2", "NB2 (Tahc/Utahc)"
    
    # 3. ตรวจสอบ NB3 (KE8, EVO, M2, BTM) ตามรูปแบบชื่อไฟล์ภาพซ้าย
    elif re.search(r'\b(KE8|M2|EVO|BTM|NB3)\b', recipe_corpus, re.IGNORECASE):
        furnace_id = "NB3"
        furnace_variant = "NB3 (BTM)" if re.search(r'\bBTM\b', recipe_corpus, re.IGNORECASE) else "NB3 (KE8 : M2/EVO)"
    
    # 4. ตรวจสอบ NB1 (CDS/KN9/12SHP)
    elif re.search(r'\b(CDS|KN9|12SHP)\b', recipe_corpus, re.IGNORECASE): 
        furnace_id, furnace_variant = "NB1", "NB1 (CDS/KN9/12SHP)"
    
    # 5. ตรวจสอบการตั้งชื่อแบบสัปดาห์ (WKxx) หากไม่เข้าเงื่อนไขด้านบน ให้เป็น NB1 Standard
    elif (re.search(r'\bWK\d{1,2}\b', recipe_corpus, re.IGNORECASE) or re.search(r'\b\d{6}\b', recipe_corpus)): 
        furnace_id, furnace_variant = "NB1", "NB1 (Standard)"
    
    # 6. ตรวจสอบจากชื่อเตาที่ระบุตรงๆ ใน Note
    else:
        f_match = re.search(r'NB\s*Furnace\s*0?([123])\b|NB\s*#?\s*0?([123])\b|NB-0?([123])\b', recipe_corpus, re.IGNORECASE)
        if f_match: 
            found_num = next(g for g in f_match.groups() if g is not None)
            furnace_id = furnace_variant = f"NB{found_num}"
    # ======================================================================
