import os
import re
import uuid
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
from contextlib import contextmanager

from flask import Flask, jsonify, render_template, request, session

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("DATA_DIR", str(BASE_DIR))).resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "chatbot.db"

app = Flask(__name__, template_folder=str(BASE_DIR / "templates"), static_folder=str(BASE_DIR / "static"))
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY", "change-this-secret-before-deploying"),
    MAX_CONTENT_LENGTH=1024 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE", "false").lower() == "true",
    PERMANENT_SESSION_LIFETIME=timedelta(days=30),
)

FALLBACK_REPLY = (
    "Humein is sawaal ka jawab abhi nahi mila hai. "
    "Hamare paas jald hi data milne ke baad aapko update kiya jayega."
)

@contextmanager
def db():
    conn = sqlite3.connect(DB_PATH, timeout=20)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db():
    with db() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            sender TEXT NOT NULL CHECK(sender IN ('user','bot')),
            message TEXT NOT NULL,
            created_at TEXT NOT NULL
        )""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_chat_session ON chat_history(session_id, id)")

def get_chat_id():
    if "chat_id" not in session:
        session["chat_id"] = uuid.uuid4().hex
    session.permanent = True
    return session["chat_id"]

def calculate(expression):
    # Intentionally support only basic arithmetic without eval().
    import ast, operator, math
    tree = ast.parse(expression, mode="eval")
    ops = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
           ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod,
           ast.Pow: operator.pow}
    def visit(node):
        if isinstance(node, ast.Expression):
            return visit(node.body)
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            value = node.value
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = (+1 if isinstance(node.op, ast.UAdd) else -1) * visit(node.operand)
        elif isinstance(node, ast.BinOp) and type(node.op) in ops:
            left, right = visit(node.left), visit(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 8:
                raise ValueError("Exponent too large")
            value = ops[type(node.op)](left, right)
        else:
            raise ValueError("Unsupported expression")
        if isinstance(value, (int, float)) and (abs(value) > 1e12 or (isinstance(value, float) and not math.isfinite(value))):
            raise ValueError("Out of range")
        return value
    return visit(tree)

def reply_for(message):
    raw = message.strip()
    q = raw.lower()
    if not raw:
        return "Please type or speak a question."

    # Greeting / common intents
    if re.search(r"\b(hi|hello|hey|namaste|नमस्ते|हेलो|हाय)\b", q):
        return "Hello! Main CodeCraft 5 hoon. Aap Python, C programming, Flask aur basic computer topics ke baare mein pooch sakte hain."
    if any(x in q for x in ["your name", "tumhara naam", "aapka naam", "who are you", "kaun ho"]):
        return "Mera naam CodeCraft 5 hai. Main Python Flask par bana ek student chatbot hoon."
    if any(x in q for x in ["time", "samay", "समय"]):
        return "Current local time: " + datetime.now().strftime("%I:%M %p")
    if any(x in q for x in ["date", "today", "aaj ki date", "तारीख"]):
        return "Aaj ki date: " + datetime.now().strftime("%d %B %Y")
    if any(x in q for x in ["thank", "धन्यवाद", "shukriya"]):
        return "You're welcome! Aur koi sawaal ho toh poochiye."
    if re.search(r"\b(bye|goodbye|अलविदा)\b", q):
        return "Goodbye! Phir milte hain."

    # Arithmetic: "calculate 24*8", "what is 2+2"
    candidate = re.sub(r"^(what is|calculate|solve|kitna hota hai)\s*", "", q).strip()
    if len(candidate) <= 80 and re.fullmatch(r"[0-9+\-*/().%\s]+", candidate) and re.search(r"\d", candidate):
        try:
            return f"{candidate} = {calculate(candidate)}"
        except ZeroDivisionError:
            return "Zero se divide nahi kar sakte."
        except Exception:
            pass

    # Local educational knowledge base (editable and deliberately limited)
    rules = [
        (["what is python", "python kya hai", "python kya hota"], "Python ek high-level, general-purpose programming language hai. Iska use web development, automation, data analysis aur AI mein hota hai."),
        (["what is flask", "flask kya hai", "flask kya hota"], "Flask Python ka lightweight web framework hai. Isse Python mein web applications aur APIs banayi ja sakti hain."),
        (["what is html", "html kya hai"], "HTML ka full form HyperText Markup Language hai. Ye web page ka structure banane ke liye use hoti hai."),
        (["what is css", "css kya hai"], "CSS ka full form Cascading Style Sheets hai. Iska use web pages ki styling, colors, spacing aur layout ke liye hota hai."),
        (["what is javascript", "javascript kya hai"], "JavaScript web pages ko interactive banati hai. Iska use browser aur server-side development dono mein hota hai."),
        (["what is variable", "variable kya hai"], "Variable ek named storage location hai jisme program data/value store karta hai."),
        (["what is loop", "loop kya hai"], "Loop kisi instruction ya code block ko baar-baar execute karta hai. Common loops: for aur while."),
        (["what is array", "array kya hai"], "Array ek data structure hai jo multiple values ko sequence mein store karta hai. C mein array ke elements same data type ke hote hain."),
        (["what is database", "database kya hai"], "Database organized data ka collection hota hai. SQLite ek lightweight relational database hai."),
        (["what is sql", "sql kya hai"], "SQL ka full form Structured Query Language hai. Iska use relational databases mein data query aur manage karne ke liye hota hai."),
        (["what is api", "api kya hai"], "API ka full form Application Programming Interface hai. Ye do software systems ko defined rules ke through communicate karne deta hai."),
        (["what is c language", "c language kya hai"], "C ek procedural, general-purpose programming language hai. Iska use system programming aur performance-focused software mein hota hai."),
        (["what is oops", "oops kya hai"], "OOP ka full form Object-Oriented Programming hai. Iske main concepts encapsulation, inheritance, polymorphism aur abstraction hain."),
        (["what is algorithm", "algorithm kya hai"], "Algorithm kisi problem ko solve karne ke liye step-by-step finite instructions ka set hota hai."),
    ]
    for phrases, answer in rules:
        if any(phrase in q for phrase in phrases):
            return answer


    # Expanded B.Tech CSE knowledge base
    extra_rules = [
        (["high level language", "high-level language", "high level programming language"],
         "A high-level programming language is designed to be easier for humans to read, write and maintain. It uses English-like keywords and abstracts many hardware details. Examples: Python, Java and C++. It generally needs a compiler or interpreter to translate the program into a form the computer can execute."),
        (["low level language", "low-level language"],
         "A low-level language is closer to the computer hardware. Machine language and assembly language are common examples. It offers more direct hardware control, but is usually harder to write and maintain than a high-level language."),
        (["difference between high level and low level", "high level vs low level"],
         "High-level languages are easier for people to read and are more portable, while low-level languages are closer to hardware and provide more direct control. Python is high-level; assembly is low-level."),
        (["what is compiler", "compiler kya hai", "compiler kya hota"],
         "A compiler translates source code into machine code or another lower-level form before execution. It commonly reports errors during the compilation process. C and C++ are commonly compiled languages."),
        (["what is interpreter", "interpreter kya hai", "interpreter kya hota"],
         "An interpreter executes a program through an interpreter runtime, often statement by statement or via an intermediate representation. Python is commonly described as an interpreted language, although its implementation also compiles source to bytecode."),
        (["compiler vs interpreter", "difference between compiler and interpreter"],
         "A compiler typically translates a program before it runs, while an interpreter executes it through a runtime. The exact distinction depends on the language implementation; Python, for example, commonly compiles to bytecode and then runs it on a virtual machine."),
        (["what is programming", "programming kya hai"],
         "Programming is the process of writing instructions that tell a computer how to perform tasks. It involves problem-solving, algorithms, writing code, testing and debugging."),
        (["what is syntax", "syntax kya hai"],
         "Syntax is the set of grammar rules of a programming language. A syntax error occurs when code does not follow those rules."),
        (["what is data type", "data types in python", "data type kya hai"],
         "A data type defines what kind of value a variable can hold and what operations are allowed. Common Python types include int, float, str, bool, list, tuple, set and dict."),
        (["what is integer", "int data type"],
         "An integer (int) is a whole number without a fractional part, such as -3, 0 or 42."),
        (["what is float", "float data type"],
         "A float represents a number with a fractional or decimal part, such as 3.14 or -0.5."),
        (["what is string", "string kya hai"],
         "A string (str) is a sequence of text characters. In Python, strings are written inside single, double or triple quotes."),
        (["what is boolean", "bool data type"],
         "A Boolean value represents truth: True or False. In Python, the type name is bool."),
        (["what is list in python", "python list"],
         "A Python list is an ordered, mutable collection. It can contain different types of values and allows duplicates. Example: numbers = [10, 20, 30]."),
        (["what is tuple", "python tuple"],
         "A tuple is an ordered, immutable collection in Python. Example: point = (3, 5)."),
        (["what is dictionary", "python dictionary", "dict in python"],
         "A Python dictionary stores key-value pairs. It is mutable and is commonly written with braces, for example: student = {'name': 'Asha', 'age': 20}."),
        (["what is set in python", "python set"],
         "A Python set is an unordered collection of unique elements. It is useful for removing duplicates and performing set operations."),
        (["what is function", "function kya hai", "python function"],
         "A function is a reusable block of code that performs a task. In Python, define one with def, for example: def greet(): print('Hello')."),
        (["what is recursion", "recursion kya hai"],
         "Recursion is a technique in which a function calls itself to solve a smaller version of a problem. It needs a base case to stop."),
        (["what is oops", "object oriented programming", "oops concept"],
         "Object-Oriented Programming (OOP) organizes software around objects created from classes. Four commonly taught principles are encapsulation, inheritance, polymorphism and abstraction."),
        (["what is class", "class in python", "class kya hai"],
         "A class is a blueprint for creating objects. It defines attributes (data) and methods (functions) that its objects can use."),
        (["what is object", "object in python", "object kya hai"],
         "An object is an instance of a class. It can contain data (attributes) and behavior (methods)."),
        (["what is inheritance", "inheritance kya hai"],
         "Inheritance lets a class derive attributes and methods from another class. It supports code reuse and relationships between classes."),
        (["what is polymorphism", "polymorphism kya hai"],
         "Polymorphism means one interface or operation can work with different underlying object types. In Python, different classes can provide methods with the same name."),
        (["what is encapsulation", "encapsulation kya hai"],
         "Encapsulation bundles data and methods together and controls how internal state is accessed or modified."),
        (["what is abstraction", "abstraction kya hai"],
         "Abstraction exposes essential features while hiding unnecessary implementation details. It helps manage complexity."),
        (["what is pointer", "pointer kya hai", "pointer in c"],
         "A pointer in C is a variable that stores the memory address of another object. The address-of operator is &, and the dereference operator is *. Example: int x=10; int *p=&x;"),
        (["what is array", "array kya hai", "array in c"],
         "An array stores a fixed-size sequence of elements of the same type in contiguous memory. In C, indexing starts at 0. Example: int marks[3] = {70, 80, 90};"),
        (["what is linked list", "linked list kya hai"],
         "A linked list is a linear data structure made of nodes. Each node stores data and a link to another node. Unlike arrays, nodes do not need to be stored contiguously."),
        (["what is stack", "stack data structure"],
         "A stack is a linear data structure that follows LIFO: Last In, First Out. Its common operations are push (insert) and pop (remove)."),
        (["what is queue", "queue data structure"],
         "A queue is a linear data structure that follows FIFO: First In, First Out. Its common operations are enqueue (insert) and dequeue (remove)."),
        (["what is tree data structure", "binary tree", "what is tree in data structure"],
         "A tree is a hierarchical data structure made of nodes connected by edges. A binary tree is a tree in which each node has at most two children."),
        (["what is graph data structure", "graph in data structure"],
         "A graph is a data structure consisting of vertices (nodes) and edges connecting them. Graphs can be directed or undirected, weighted or unweighted."),
        (["what is searching", "linear search", "binary search"],
         "Searching is the process of finding a target value in a collection. Linear search checks items one by one; binary search repeatedly halves a sorted search range and runs in O(log n) time."),
        (["what is sorting", "sorting algorithm"],
         "Sorting arranges data in a chosen order, such as ascending or descending. Common algorithms include bubble sort, selection sort, insertion sort, merge sort and quicksort."),
        (["what is algorithm", "algorithm kya hai"],
         "An algorithm is a finite, ordered set of clear steps for solving a problem. A good algorithm is correct and should use resources efficiently."),
        (["what is time complexity", "time complexity kya hai", "big o notation"],
         "Time complexity describes how an algorithm's running time grows as input size grows. Big-O notation expresses an upper-bound growth rate, such as O(1), O(n), O(log n) or O(n²)."),
        (["what is operating system", "operating system kya hai", "os kya hai"],
         "An operating system (OS) manages computer hardware and software resources and provides services to programs. Examples include Windows, macOS and Linux."),
        (["what is process", "process in operating system"],
         "A process is a program in execution. It has its own process state and resources, such as memory and execution context."),
        (["what is thread", "thread in operating system"],
         "A thread is a unit of execution within a process. Threads in the same process typically share its memory and resources."),
        (["process vs thread", "difference between process and thread"],
         "A process is an executing program with its own address space and resources. A thread is a smaller execution unit inside a process; threads of one process usually share memory."),
        (["what is deadlock", "deadlock in operating system"],
         "A deadlock is a situation where processes wait indefinitely for resources held by one another. The four classic conditions are mutual exclusion, hold and wait, no preemption and circular wait."),
        (["what is database", "database kya hai"],
         "A database is an organized collection of data that can be stored, queried and updated. A DBMS is software used to manage databases."),
        (["what is dbms", "dbms kya hai"],
         "DBMS stands for Database Management System. It is software for creating, storing, retrieving and managing data in databases. Examples include MySQL, PostgreSQL and SQLite."),
        (["what is primary key", "primary key in dbms"],
         "A primary key is a column or set of columns that uniquely identifies each row in a table. It must be unique and cannot contain NULL values."),
        (["what is foreign key", "foreign key in dbms"],
         "A foreign key is a column or set of columns that references a key in another (or the same) table, helping maintain referential integrity."),
        (["what is sql", "sql kya hai"],
         "SQL stands for Structured Query Language. It is used to define, query and manipulate data in relational database systems."),
        (["what is normalization", "normalization in dbms"],
         "Database normalization organizes relational tables to reduce unnecessary duplication and update anomalies. Common normal forms include 1NF, 2NF and 3NF."),
        (["what is computer network", "computer networking", "network kya hai"],
         "A computer network is a group of connected devices that exchange data and share resources using communication protocols."),
        (["what is ip address", "ip address kya hai"],
         "An IP address is a logical address used to identify an interface on an IP network. IPv4 uses 32 bits; IPv6 uses 128 bits."),
        (["what is http", "http kya hai"],
         "HTTP (Hypertext Transfer Protocol) is an application-layer protocol used for communication between web clients and servers. HTTPS is HTTP protected by TLS."),
        (["what is html", "html kya hai"],
         "HTML stands for HyperText Markup Language. It describes the structure and content of web pages using elements such as headings, paragraphs, links and images."),
        (["what is css", "css kya hai"],
         "CSS stands for Cascading Style Sheets. It controls the presentation of web pages, including colors, fonts, spacing and layout."),
        (["what is javascript", "javascript kya hai"],
         "JavaScript is a programming language commonly used to make web pages interactive. It also runs on servers and other platforms."),
        (["what is flask", "flask kya hai"],
         "Flask is a lightweight Python web framework. It provides routing and request/response handling and can be extended with additional packages."),
        (["what is api", "api kya hai"],
         "API stands for Application Programming Interface. It defines how software components communicate through agreed operations and data formats."),
        (["what is cybersecurity", "cyber security kya hai"],
         "Cybersecurity is the practice of protecting systems, networks and data from unauthorized access, damage and disruption."),
        (["what is cloud computing", "cloud computing kya hai"],
         "Cloud computing provides computing resources—such as servers, storage and databases—over a network on demand. Common service models include IaaS, PaaS and SaaS."),
        (["what is machine learning", "machine learning kya hai"],
         "Machine learning is a field of AI in which systems learn patterns from data to make predictions or decisions, rather than relying only on hand-written rules."),
        (["what is artificial intelligence", "what is ai", "artificial intelligence kya hai"],
         "Artificial Intelligence (AI) is the broad field of building computer systems that perform tasks associated with human intelligence, such as language understanding, perception and decision-making."),
    ]
    for phrases, answer in extra_rules:
        if any(phrase in q for phrase in phrases):
            return answer

    return FALLBACK_REPLY

@app.route("/")
def home():
    sid = get_chat_id()
    with db() as conn:
        messages = conn.execute(
            "SELECT sender, message, created_at FROM chat_history WHERE session_id=? ORDER BY id",
            (sid,)
        ).fetchall()
    return render_template("chat.html", messages=messages)

@app.route("/api/chat", methods=["POST"])
def chat_api():
    payload = request.get_json(silent=True) or {}
    message = payload.get("message", "")
    if not isinstance(message, str):
        return jsonify(error="Message must be text."), 400
    message = message.strip()
    if not message:
        return jsonify(error="Please type or speak a question."), 400
    if len(message) > 2000:
        return jsonify(error="Message is too long (maximum 2,000 characters)."), 400

    reply = reply_for(message)
    sid = get_chat_id()
    now = datetime.now().strftime("%I:%M %p")
    with db() as conn:
        conn.execute("INSERT INTO chat_history(session_id,sender,message,created_at) VALUES(?,?,?,?)",
                     (sid, "user", message, now))
        conn.execute("INSERT INTO chat_history(session_id,sender,message,created_at) VALUES(?,?,?,?)",
                     (sid, "bot", reply, now))
    return jsonify(reply=reply, created_at=now)

@app.route("/api/clear", methods=["POST"])
def clear_chat():
    sid = get_chat_id()
    with db() as conn:
        conn.execute("DELETE FROM chat_history WHERE session_id=?", (sid,))
    return jsonify(status="cleared")

@app.route("/healthz")
def healthz():
    return jsonify(status="ok", mode="free-local-knowledge-base")

@app.errorhandler(413)
def too_large(_error):
    return jsonify(error="Request too large."), 413

init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5002")), debug=False)
