#!/usr/bin/env python3
"""Debug script to check the generated image prompt."""

import json
from google import genai
from config.settings import validate_config
from agents.image_agent import _call_gemini_analyze, build_image_prompt

# Sample LinkedIn post from our run
linkedin_post = """Most people pay for monthly AI subscriptions that cost money without generating a single dollar back. 

The reason most AI monetization ideas fail comes down to one simple flaw: no one can clearly explain who the customer is and why they would pay you.

Building a sustainable service or business using AI isn't about shiny tools—it's about filling the gap between what AI can output and what a business actually needs. 

Every viable AI offer relies on four foundational elements:
1. What you actually do
2. The specific AI tools required
3. Who pays you for it
4. Your unit economics (Cost vs. What you charge)

Here are the key strategic takeaways for monetizing AI effectively today:

• **Sell taste, not raw generation:** AI video, image, and copy tools are becoming commoditized or built directly into ad platforms. The value isn't in creating raw assets; it's in curation, quality control, and knowing what works. 

• **The "80/20 Trap" in app development:** Low-code and AI builder tools (like Google AI Studio or Lovable) can build 80% of a functional prototype in minutes. The remaining 20%—calendar syncs, payment integrations, edge cases, and client-specific logic—is the actual work businesses pay for.

• **Niche focus beats generic offerings:** A generic AI voice agent competes with tens of thousands of listings. A voice agent custom-built strictly for one specific industry (like trucking or local service bookings) competes with almost no one. 

• **Implementation over deliverables:** Most professionals use LLMs like basic search engines, unaware of built-in features like team projects or custom skills. Setting up an organization's existing workflows or conducting team workshops taps directly into pre-approved corporate training budgets.

• **Boring services create reliable retainers:** Automating back-office paperwork, incoming phone routing, or lead list research using tools like Zapier, N8N, or Clay creates long-term retainer revenue. The real moat in these services is trust and consistency, not complexity.

Ultimately, tools can handle the output, but clients pay for solved problems, workflow integration, and human judgment. 

Focus on one specific problem for one target audience, build a reliable system behind it, and sell the outcome."""

try:
    config = validate_config()
    print("=" * 80)
    print("STEP 1: Gemini Analysis")
    print("=" * 80)
    
    analysis_text = _call_gemini_analyze(config["GEMINI_API_KEY"], linkedin_post)
    print("Raw Analysis Output:")
    print(analysis_text)
    print("\n" + "=" * 80)
    
    analysis = json.loads(analysis_text)
    print("\nParsed Analysis:")
    print(json.dumps(analysis, indent=2))
    
    print("\n" + "=" * 80)
    print("STEP 2: Generated Image Prompt")
    print("=" * 80)
    
    prompt = build_image_prompt(linkedin_post, analysis)
    print(prompt)
    
    print("\n" + "=" * 80)
    print(f"Prompt length: {len(prompt)} characters")
    print("=" * 80)
    
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
