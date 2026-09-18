def build_interactive_payload(recipient_number: str, body_text: str, options: list, menu_title: str = "Select Option") -> dict:
    """
    Universal interactive payload generator.
    'options' is a list of dicts: [{"id": "val1", "title": "Option 1"}, ...]
    - Meta API allows max 3 buttons for 'button' type.
    - Meta API allows max 10 options for 'list' type.
    This function automatically switches between Button and List based on the number of options (1 to 10).
    """
    if not options or len(options) > 10:
        raise ValueError("Bhai Meta API maximum 10 options allow karti hai.")

    if len(options) <= 3:
        # 1, 2, ya 3 options ke liye Normal Buttons
        buttons = []
        for opt in options:
            buttons.append({
                "type": "reply",
                "reply": {
                    "id": str(opt["id"]),
                    "title": str(opt["title"])
                }
            })
        
        return {
            "messaging_product": "whatsapp",
            "to": recipient_number,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": body_text},
                "action": {
                    "buttons": buttons
                }
            }
        }
    else:
        # 4 se 10 options ke liye List Menu (Radio buttons style)
        rows = []
        for opt in options:
            rows.append({"id": str(opt["id"]), "title": str(opt["title"])})

        return {
            "messaging_product": "whatsapp",
            "to": recipient_number,
            "type": "interactive",
            "interactive": {
                "type": "list",
                "body": {"text": body_text},
                "action": {
                    "button": menu_title,
                    "sections": [
                        {
                            "title": "Available Options",
                            "rows": rows
                        }
                    ]
                }
            }
        }

def build_document_payload(recipient_number: str, media_id: str, filename: str, caption: str = "") -> dict:
    return {
        "messaging_product": "whatsapp",
        "to": recipient_number,
        "type": "document",
        "document": {
            "id": media_id,
            "filename": filename,
            "caption": caption
        }
    }


#================= PAYLOAD DEMOS ===============
Payloads_For_Three_INTERACTIVE = {
  "messaging_product": "whatsapp",
  "to": "919876543210",
  "type": "interactive",
  "interactive": {
    "type": "button",
    "body": {
      "text": "Bhai kya karna hai?"
    },
    "action": {
      "buttons": [
        {
          "type": "reply",
          "reply": {
            "id": "btn_1",
            "title": "Ek"
          }
        },
        {
          "type": "reply",
          "reply": {
            "id": "btn_2",
            "title": "Do"
          }
        },
        {
          "type": "reply",
          "reply": {
            "id": "btn_3",
            "title": "Teen"
          }
        }
      ]
    }
  }
}

Payloads_For_TEN_INTERACTIVE = {
  "messaging_product": "whatsapp",
  "to": "919876543210",
  "type": "interactive",
  "interactive": {
    "type": "list",
    "body": {
      "text": "Bhai kya karna hai?"
    },
    "action": {
      "button": "Select Option", # <--- YAHAN AATA HAI WO MENU_TITLE JISKI WAJAH SE MAIN FASA THA
      "sections": [
        {
          "title": "Available Options",
          "rows": [
            {
              "id": "btn_1",
              "title": "Ek"
            },
            {
              "id": "btn_2",
              "title": "Do"
            },
            {
              "id": "btn_3",
              "title": "Teen"
            },
            {
              "id": "btn_4",
              "title": "Chaar"
            },
            {
              "id": "btn_5",
              "title": "Paanch"
            }
          ]
        }
      ]
    }
  }
}