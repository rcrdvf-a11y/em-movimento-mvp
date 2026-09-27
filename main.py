import sqlite3
from fastapi import FastAPI, Request, Form
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse

app = FastAPI(title="Em Movimento")

# Comando que libera a pasta de imagens para o site
app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")

# 1. Função para conectar ao banco
def conectar_banco():
    conn = sqlite3.connect("banco.db")
    conn.row_factory = sqlite3.Row
    return conn

# 2. Cria as TRÊS tabelas do nosso sistema
def criar_tabelas():
    conn = conectar_banco()
    
    # Tabela de Usuários
    conn.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT,
            email TEXT UNIQUE,
            senha TEXT
        )
    ''')
    
    # Tabela de Eventos (atualizada com o campo status)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS eventos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            titulo TEXT,
            data TEXT,
            cidade TEXT,
            distancia TEXT,
            link_mapa TEXT,
            status TEXT DEFAULT 'pendente',
            criador_id INTEGER,
            FOREIGN KEY(criador_id) REFERENCES usuarios(id)
        )
    ''')
    
    # Tabela de Inscrições
    conn.execute('''
        CREATE TABLE IF NOT EXISTS inscricoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER,
            evento_id INTEGER,
            FOREIGN KEY(usuario_id) REFERENCES usuarios(id),
            FOREIGN KEY(evento_id) REFERENCES eventos(id)
        )
    ''')
    
    conn.commit()
    conn.close()

# Roda a função para garantir que o banco existe
criar_tabelas()

# ---------------------------------------------------------
# ROTAS DE ADMINISTRAÇÃO
# ---------------------------------------------------------

@app.get("/admin")
def painel_admin(request: Request):
    usuario_id = request.cookies.get("usuario_id")
    
    if not usuario_id:
        return RedirectResponse(url="/login", status_code=303)
        
    conn = conectar_banco()
    usuario = conn.execute("SELECT * FROM usuarios WHERE id = ?", (usuario_id,)).fetchone()
    
    # Validação rigorosa: Apenas o e-mail de administração acessa
    if not usuario or usuario["email"] != "admin@pedal.com":
        conn.close()
        return RedirectResponse(url="/", status_code=303)
    
    # Busca apenas os eventos que aguardam aprovação
    cursor = conn.execute("SELECT * FROM eventos WHERE status = 'pendente'")
    eventos_pendentes = cursor.fetchall()
    conn.close()
    
    return templates.TemplateResponse(
        request=request, 
        name="admin.html",
        context={"usuario": usuario, "eventos_pendentes": eventos_pendentes}
    )

@app.get("/aprovar/{evento_id}")
def aprovar_evento(request: Request, evento_id: int):
    usuario_id = request.cookies.get("usuario_id")
    if not usuario_id:
        return RedirectResponse(url="/login", status_code=303)
        
    conn = conectar_banco()
    usuario = conn.execute("SELECT email FROM usuarios WHERE id = ?", (usuario_id,)).fetchone()
    
    if usuario and usuario["email"] == "admin@pedal.com":
        conn.execute("UPDATE eventos SET status = 'aprovado' WHERE id = ?", (evento_id,))
        conn.commit()
        
    conn.close()
    return RedirectResponse(url="/admin", status_code=303)

@app.get("/recusar/{evento_id}")
def recusar_evento(request: Request, evento_id: int):
    usuario_id = request.cookies.get("usuario_id")
    if not usuario_id:
        return RedirectResponse(url="/login", status_code=303)
        
    conn = conectar_banco()
    usuario = conn.execute("SELECT email FROM usuarios WHERE id = ?", (usuario_id,)).fetchone()
    
    if usuario and usuario["email"] == "admin@pedal.com":
        # Se recusar, o evento é apagado da fila
        conn.execute("DELETE FROM eventos WHERE id = ?", (evento_id,))
        conn.commit()
        
    conn.close()
    return RedirectResponse(url="/admin", status_code=303)

# ---------------------------------------------------------
# ROTAS DE EVENTOS E INSCRIÇÕES
# ---------------------------------------------------------

@app.get("/")
def pagina_inicial(request: Request):
    conn = conectar_banco()
    
    # Pega apenas eventos aprovados
    cursor_eventos = conn.execute("SELECT * FROM eventos WHERE status = 'aprovado'")
    eventos_db = cursor_eventos.fetchall()
    
    usuario_id = request.cookies.get("usuario_id")
    usuario_logado = None
    
    if usuario_id:
        cursor_usuario = conn.execute("SELECT * FROM usuarios WHERE id = ?", (usuario_id,))
        usuario_logado = cursor_usuario.fetchone()
        
    conn.close()
    
    return templates.TemplateResponse(
        request=request, 
        name="index.html",
        context={"eventos": eventos_db, "usuario": usuario_logado}
    )

@app.post("/")
def adicionar_evento(
    request: Request,
    titulo: str = Form(...),
    data: str = Form(...),
    cidade: str = Form(...),
    distancia: str = Form(...),
    link_mapa: str = Form("")
):
    usuario_id = request.cookies.get("usuario_id")
    if not usuario_id:
        return RedirectResponse(url="/login", status_code=303)
        
    conn = conectar_banco()
    conn.execute(
        "INSERT INTO eventos (titulo, data, cidade, distancia, link_mapa, status, criador_id) VALUES (?, ?, ?, ?, ?, 'pendente', ?)", 
        (titulo, data, cidade, distancia, link_mapa, usuario_id)
    )
    conn.commit()
    conn.close()
    
    return RedirectResponse(url="/", status_code=303)

@app.get("/deletar/{evento_id}")
def deletar_evento(request: Request, evento_id: int):
    usuario_id = request.cookies.get("usuario_id")
    if not usuario_id:
        return RedirectResponse(url="/login", status_code=303)
        
    conn = conectar_banco()
    cursor = conn.execute("SELECT * FROM eventos WHERE id = ?", (evento_id,))
    evento = cursor.fetchone()
    
    if evento and str(evento["criador_id"]) == str(usuario_id):
        cursor_inscritos = conn.execute('''
            SELECT usuarios.nome, usuarios.email 
            FROM inscricoes 
            JOIN usuarios ON inscricoes.usuario_id = usuarios.id 
            WHERE inscricoes.evento_id = ?
        ''', (evento_id,))
        inscritos = cursor_inscritos.fetchall()
        
        print("\n--- INÍCIO DOS AVISOS DE CANCELAMENTO ---")
        for inscrito in inscritos:
            print(f"📧 Enviando e-mail para: {inscrito['email']}")
            print(f"   Mensagem: Olá {inscrito['nome']}, o evento '{evento['titulo']}' foi cancelado pelo organizador.")
        print("--- FIM DOS AVISOS ---\n")
        
        conn.execute("DELETE FROM inscricoes WHERE evento_id = ?", (evento_id,))
        conn.execute("DELETE FROM eventos WHERE id = ?", (evento_id,))
        conn.commit()
        
    conn.close()
    return RedirectResponse(url="/", status_code=303)

@app.get("/participar/{evento_id}")
def participar_evento(request: Request, evento_id: int):
    usuario_id = request.cookies.get("usuario_id")
    if not usuario_id:
        return RedirectResponse(url="/login", status_code=303)
        
    conn = conectar_banco()
    cursor = conn.execute("SELECT * FROM inscricoes WHERE usuario_id = ? AND evento_id = ?", (usuario_id, evento_id))
    ja_inscrito = cursor.fetchone()
    
    if not ja_inscrito:
        conn.execute("INSERT INTO inscricoes (usuario_id, evento_id) VALUES (?, ?)", (usuario_id, evento_id))
        conn.commit()
        
    conn.close()
    return RedirectResponse(url="/", status_code=303)

@app.get("/editar/{evento_id}")
def pagina_editar(request: Request, evento_id: int):
    usuario_id = request.cookies.get("usuario_id")
    if not usuario_id:
        return RedirectResponse(url="/login", status_code=303)
        
    conn = conectar_banco()
    cursor = conn.execute("SELECT * FROM eventos WHERE id = ?", (evento_id,))
    evento = cursor.fetchone()
    conn.close()
    
    if not evento or str(evento["criador_id"]) != str(usuario_id):
        return RedirectResponse(url="/", status_code=303)
        
    return templates.TemplateResponse(
        request=request, 
        name="editar.html",
        context={"evento": evento}
    )

@app.post("/editar/{evento_id}")
def salvar_edicao(
    request: Request,
    evento_id: int,
    titulo: str = Form(...),
    data: str = Form(...),
    cidade: str = Form(...),
    distancia: str = Form(...),
    link_mapa: str = Form("")
):
    usuario_id = request.cookies.get("usuario_id")
    if not usuario_id:
        return RedirectResponse(url="/login", status_code=303)
        
    conn = conectar_banco()
    cursor = conn.execute("SELECT criador_id FROM eventos WHERE id = ?", (evento_id,))
    evento_bd = cursor.fetchone()
    
    if evento_bd and str(evento_bd["criador_id"]) == str(usuario_id):
        conn.execute(
            "UPDATE eventos SET titulo = ?, data = ?, cidade = ?, distancia = ?, link_mapa = ? WHERE id = ?",
            (titulo, data, cidade, distancia, link_mapa, evento_id)
        )
        conn.commit()
    
    conn.close()
    return RedirectResponse(url="/", status_code=303)

# ---------------------------------------------------------
# ROTAS DE USUÁRIO E PAINEL
# ---------------------------------------------------------

@app.get("/sair")
def sair():
    resposta = RedirectResponse(url="/", status_code=303)
    resposta.delete_cookie("usuario_id")
    return resposta

@app.post("/cadastrar")
def cadastrar_usuario(
    nome: str = Form(...),
    email: str = Form(...),
    senha: str = Form(...)
):
    conn = conectar_banco()
    conn.execute(
        "INSERT INTO usuarios (nome, email, senha) VALUES (?, ?, ?)", 
        (nome, email, senha)
    )
    conn.commit()
    conn.close()
    return RedirectResponse(url="/", status_code=303)

@app.get("/login")
def pagina_login(request: Request):
    return templates.TemplateResponse(
        request=request, 
        name="login.html"
    )

@app.post("/login")
def fazer_login(
    email_login: str = Form(...),
    senha_login: str = Form(...)
):
    conn = conectar_banco()
    cursor = conn.execute(
        "SELECT * FROM usuarios WHERE email = ? AND senha = ?", 
        (email_login, senha_login)
    )
    usuario = cursor.fetchone()
    conn.close()
    
    if usuario:
        resposta = RedirectResponse(url="/", status_code=303)
        resposta.set_cookie(key="usuario_id", value=str(usuario["id"]))
        return resposta
    else:
        return "E-mail ou senha incorretos. Clique em 'Voltar' no navegador e tente novamente."

@app.get("/painel")
def painel_usuario(request: Request):
    usuario_id = request.cookies.get("usuario_id")
    
    if not usuario_id:
        return RedirectResponse(url="/login", status_code=303)
        
    conn = conectar_banco()
    usuario = conn.execute("SELECT * FROM usuarios WHERE id = ?", (usuario_id,)).fetchone()
    
    cursor_org = conn.execute("SELECT * FROM eventos WHERE criador_id = ?", (usuario_id,))
    eventos_organizados = [dict(row) for row in cursor_org.fetchall()]
    
    for evento in eventos_organizados:
        cursor_inscritos = conn.execute('''
            SELECT usuarios.nome, usuarios.email 
            FROM inscricoes 
            JOIN usuarios ON inscricoes.usuario_id = usuarios.id 
            WHERE inscricoes.evento_id = ?
        ''', (evento["id"],))
        evento["inscritos"] = cursor_inscritos.fetchall()
        
    cursor_part = conn.execute('''
        SELECT eventos.* 
        FROM inscricoes 
        JOIN eventos ON inscricoes.evento_id = eventos.id 
        WHERE inscricoes.usuario_id = ?
    ''', (usuario_id,))
    eventos_participo = cursor_part.fetchall()
    
    conn.close()
    
    return templates.TemplateResponse(
        request=request, 
        name="painel.html",
        context={
            "usuario": usuario, 
            "organizados": eventos_organizados, 
            "participo": eventos_participo
        }
    )