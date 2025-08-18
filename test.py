import requests

prompt = '''You are a domain-agnostic AI assistant specialized in transforming raw text into structured knowledge.
Your task is to read the following input and generate a clean, diverse set of Question-Answer (Q&A) pairs.
Instructions:
- Generate at least 50 meaningful Q&A pairs.
- Cover all important points, facts, sections, or ideas in the text, including numbers.
- Rephrase questions naturally.
- Avoid vague or repetitive questions.
- Format the output as a JSON array:
[
  {{"question": "...", "answer": "..."}},
  ...
] WELCOME TO MY WORLD Hi, I’m Ahmed Raza a Developer. I help brands grow with cutting-edge web & app solutions, stunning designs, and seamless user experiences—let’s bring your vision to life! Together, we can turn ideas into impactful digital realities LET'S GET CONNECTED LET'S GET CONNECTED 2+ Years of Experienc 20+ Successful Projects20+ Satisfied Clients SERVICES What I Do Web DevelopmentBuilding high-performance, responsive, and visually stunning websites that enhance user experience and brand identity. App Development Crafting innovative mobile and desktop applications with seamless functionality and modern UI/UX design. Graphic Design Creating eye-catching visuals, brand assets, and UI designs that captivate audiences and drive engagement.Branding & Identity Elevating businesses with strategic branding, logo design, and a cohesive digital presence.UI/UX Design Designing intuitive, user-friendly interfaces that provide a seamless and engaging user experience.'''
r= requests.post(
    "http://103.176.204.44:11434/api/generate",
    json={"model": "llama3:instruct", "prompt": prompt, "stream": False}
)
print(r.status_code, r.text)
