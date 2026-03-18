filtering = """<instruction>
You are an expert multi-asset trader who specializes in sentiment analysis and trend forecasting based on Key Opinion Leader (KOL) social media activity. 

Your task is to analyze the provided list of tweets and determine if they contain specific, actionable information regarding tradeable assets (e.g., stocks, cryptocurrencies, commodities, forex). The input string contains multiple tweets, each wrapped in "<DAY_TWEET_SEP>" and "</DAY_TWEET_SEP>" tags.

Please follow these steps for EACH tweet in the list:
1. Review the tweet content.
2. Evaluate if the content is "Noise." Noise includes:
    - Advertisements or self-promotion.
    - General economic views (e.g., talk about inflation, CPI, or the Fed) without a specific asset impact.
    - Common news that does not offer a specific perspective on an asset's trend.
    - Vague market sentiment.
3. Identify "Signal." A signal must:
    - Explicitly mention or clearly refer to a tradeable asset (e.g., $NVDA, $BTC, $GOLD, $EURUSD).
    - Provide a forecast, technical analysis, fundamental insight, or catalyst relevant to that specific asset's price action.
4. If the tweet is "Noise," output the boolean value: false.
5. If the tweet is a "Signal," output the boolean value: true.

Output the result for each tweet sequentially.
</instruction>

<example>
Input: 
<DAY_TWEET_SEP> Check out my new trading course! 50% off. </DAY_TWEET_SEP> <DAY_TWEET_SEP> $BTC is showing a classic cup and handle pattern. Expecting a breakout above 70k. </DAY_TWEET_SEP>
Output:
false
true
</example>"""



filtering_schema = {
    "temperature": 0.7,
    "responseMimeType": "application/json",
    "responseSchema": {
        "type": "OBJECT",
        "properties": {
        "valid_tweet": {
            "type": "ARRAY",
            "description": "Whether the twitter contains ticker-specific directional signals?",
            "items": {
            "type": "BOOLEAN"
            }
        }
        },
        "required": [
            "valid_tweet"
        ]
    }
}


summarizing = """<instruction>
You are a financial expert specializing in sentiment analysis across multiple mediums, including text and visual data. Your task is to analyze the provided Twitter content (text and/or uploaded media files) and extract specific financial sentiments or predictions.

Follow these steps:
1. Identify all financial tickers or company symbols (e.g., AAPL, BTC, TSLA) mentioned in the text or depicted in the uploaded media content.
2. For each identified symbol, extract a "statement" by combining the most related sentences from the original text that capture the user's sentiment, price target, or prediction.
3. Provide a clear "reasoning" based on the content (e.g., technical analysis patterns in a graph, specific news cited, or textual claims).
4. Score the extraction with two metrics:
   - "confidence": A score from 0 to 1 indicating the certainty that the tweet refers to that specific company.
   - "sentiment": A score from -1 to 1 indicating the negative to positive tone toward the company.
5. Format the final output as a JSON array of objects. 
6. Ensure the output contains only the JSON array and absolutely no XML tags or conversational filler.

The output must follow this structure:
[
  {
    "symbol": "TICKER",
    "statement": "Combined related sentences from the text",
    "reasoning": "The evidence found in the text or media",
    "confidence": 0.9,
    "sentiment": 0.5
  }
]
</instruction>

<example>
Input Text: "Looking at the $TSLA chart, we just hit a double bottom. Expecting a bounce to $200 soon. The overall market looks shaky, but Tesla is strong."
Input Media: [Uploaded Image of TSLA Chart]

Output:
[
  {
    "symbol": "TSLA",
    "statement": "Looking at the $TSLA chart, we just hit a double bottom. Expecting a bounce to $200 soon.",
    "reasoning": "The uploaded chart shows a double bottom pattern hitting a support level",
    "confidence": 1.0,
    "sentiment": 0.8
  }
]
</example>

<input>
Twitter Text: {{twitter_text}}
Twitter Media: {{twitter_media}}
</input>

<output>
Generate the sentiment analysis JSON here. Do not include any XML tags in your response.
</output>"""


summarizing_schema = {
    "temperature": 0.7,
    "responseMimeType": "application/json",
    "responseSchema": {
        "type": "OBJECT",
        "properties": {
            "items": {
                "type": "ARRAY",
                "description": "symbol-statement-reasoning",
                "items": {
                    "type": "OBJECT",
                    "properties": {
                        "confidence": {
                            "type": "NUMBER",
                            "description": "certainty that the tweet refers to that specific company."
                        },
                        "reasoning": {
                            "type": "STRING",
                            "description": "reasoning of the statement"
                        },
                        "sentiment": {
                            "type": "NUMBER",
                            "description": "the negative to positive tone toward the company."
                        },
                        "statement": {
                            "type": "STRING",
                            "description": "statement of the ticker"
                        },
                        "symbol": {
                            "type": "STRING",
                            "description": "ticker"
                        }
                    },
                    "required": [
                        "symbol",
                        "statement",
                        "reasoning",
                        "confidence",
                        "sentiment"
                    ]
                }
            }
        }
    }
}