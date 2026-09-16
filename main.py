import sqlite3
from fastapi import FastAPI, Request, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse

app = FastAPI(title="Em Movimento")
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
    
    # Tabela de Eventos (agora tem o criador_id)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS eventos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            titulo TEXT,
            data TEXT,
            cidade TEXT,
            distancia TEXT,
            criador_id INTEGER,
            FOREIGN KEY(criador_id) REFERENCES usuarios(id)
        )
    ''')
    
    # Tabela de Inscrições (A ponte entre o usuário e o evento)
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
# ROTAS DE EVENTOS E INSCRIÇÕES
# ---------------------------------------------------------

# Rota GET: Lê os eventos e descobre quem é o usuário
@app.get("/")
def pagina_inicial(request: Request):
    conn = conectar_banco()
    
    # Pega todos os eventos
    cursor_eventos = conn.execute("SELECT * FROM eventos")
    eventos_db = cursor_eventos.fetchall()
    
    # Verifica se existe um "carimbo" (cookie) de usuário no navegador
    usuario_id = request.cookies.get("usuario_id")
    usuario_logado = None
    
    # Se tiver carimbo, vamos buscar o nome da pessoa no banco de dados!
    if usuario_id:
        cursor_usuario = conn.execute("SELECT * FROM usuarios WHERE id = ?", (usuario_id,))
        usuario_logado = cursor_usuario.fetchone()
        
    conn.close()
    
    # Enviamos para o HTML a lista de eventos e também os dados do usuário (se houver)
    return templates.TemplateResponse(
        request=request, 
        name="index.html",
        context={"eventos": eventos_db, "usuario": usuario_logado}
    )

# Rota POST: Salva um novo evento vinculando ao criador real
@app.post("/")
def adicionar_evento(
    request: Request,
    titulo: str = Form(...),
    data: str = Form(...),
    cidade: str = Form(...),
    distancia: str = Form(...)
):
    usuario_id = request.cookies.get("usuario_id")
    
    # Segurança extra: se tentar criar evento sem login, é barrado
    if not usuario_id:
        return RedirectResponse(url="/login", status_code=303)
        
    conn = conectar_banco()
    # Inserimos o evento passando o ID real do usuário que está logado
    conn.execute(
        "INSERT INTO eventos (titulo, data, cidade, distancia, criador_id) VALUES (?, ?, ?, ?, ?)", 
        (titulo, data, cidade, distancia, usuario_id)
    )
    conn.commit()
    conn.close()
    
    return RedirectResponse(url="/", status_code=303)


# Rota para deletar (Agora com Segurança e Simulação de E-mail!)
@app.get("/deletar/{evento_id}")
def deletar_evento(request: Request, evento_id: int):
    usuario_id = request.cookies.get("usuario_id")
    if not usuario_id:
        return RedirectResponse(url="/login", status_code=303)
        
    conn = conectar_banco()
    
    # 1. Verifica quem é o dono do evento
    cursor = conn.execute("SELECT * FROM eventos WHERE id = ?", (evento_id,))
    evento = cursor.fetchone()
    
    # 2. Segurança: Só apaga se o usuário logado for o criador do evento
    if evento and str(evento["criador_id"]) == str(usuario_id):
        
        # 3. Buscar os inscritos para avisar do cancelamento
        cursor_inscritos = conn.execute('''
            SELECT usuarios.nome, usuarios.email 
            FROM inscricoes 
            JOIN usuarios ON inscricoes.usuario_id = usuarios.id 
            WHERE inscricoes.evento_id = ?
        ''', (evento_id,))
        inscritos = cursor_inscritos.fetchall()
        
        # Simula o envio do e-mail no terminal
        print("\n--- INÍCIO DOS AVISOS DE CANCELAMENTO ---")
        for inscrito in inscritos:
            print(f"📧 Enviando e-mail para: {inscrito['email']}")
            print(f"   Mensagem: Olá {inscrito['nome']}, o evento '{evento['titulo']}' foi cancelado pelo organizador.")
        print("--- FIM DOS AVISOS ---\n")
        
        # 4. Limpa as inscrições e apaga o evento
        conn.execute("DELETE FROM inscricoes WHERE evento_id = ?", (evento_id,))
        conn.execute("DELETE FROM eventos WHERE id = ?", (evento_id,))
        conn.commit()
        
    conn.close()
    return RedirectResponse(url="/", status_code=303)


# Rota para Participar de um Evento
@app.get("/participar/{evento_id}")
def participar_evento(request: Request, evento_id: int):
    usuario_id = request.cookies.get("usuario_id")
    if not usuario_id:
        return RedirectResponse(url="/login", status_code=303)
        
    conn = conectar_banco()
    
    # Verifica se o usuário já está inscrito para não duplicar
    cursor = conn.execute("SELECT * FROM inscricoes WHERE usuario_id = ? AND evento_id = ?", (usuario_id, evento_id))
    ja_inscrito = cursor.fetchone()
    
    # Se não estiver inscrito, nós o adicionamos!
    if not ja_inscrito:
        conn.execute("INSERT INTO inscricoes (usuario_id, evento_id) VALUES (?, ?)", (usuario_id, evento_id))
        conn.commit()
        
    conn.close()
    return RedirectResponse(url="/", status_code=303)

# ---------------------------------------------------------
# ROTA DE EDIÇÃO (O "Update" do CRUD)
# ---------------------------------------------------------

# Rota GET: Mostra a tela de edição com os dados atuais preenchidos
@app.get("/editar/{evento_id}")
def pagina_editar(request: Request, evento_id: int):
    usuario_id = request.cookies.get("usuario_id")
    if not usuario_id:
        return RedirectResponse(url="/login", status_code=303)
        
    conn = conectar_banco()
    cursor = conn.execute("SELECT * FROM eventos WHERE id = ?", (evento_id,))
    evento = cursor.fetchone()
    conn.close()
    
    # Segurança: Se o evento não existir ou não for da pessoa logada, chuta de volta
    if not evento or str(evento["criador_id"]) != str(usuario_id):
        return RedirectResponse(url="/", status_code=303)
        
    return templates.TemplateResponse(
        request=request, 
        name="editar.html",
        context={"evento": evento}
    )

# Rota POST: Salva as alterações feitas
@app.post("/editar/{evento_id}")
def salvar_edicao(
    request: Request,
    evento_id: int,
    titulo: str = Form(...),
    data: str = Form(...),
    cidade: str = Form(...),
    distancia: str = Form(...)
):
    usuario_id = request.cookies.get("usuario_id")
    if not usuario_id:
        return RedirectResponse(url="/login", status_code=303)
        
    conn = conectar_banco()
    # Verifica segurança novamente
    cursor = conn.execute("SELECT criador_id FROM eventos WHERE id = ?", (evento_id,))
    evento_bd = cursor.fetchone()
    
    if evento_bd and str(evento_bd["criador_id"]) == str(usuario_id):
        # O comando UPDATE altera dados que já existem na tabela
        conn.execute(
            "UPDATE eventos SET titulo = ?, data = ?, cidade = ?, distancia = ? WHERE id = ?",
            (titulo, data, cidade, distancia, evento_id)
        )
        conn.commit()
    
    conn.close()
    return RedirectResponse(url="/", status_code=303)

# ---------------------------------------------------------
# ROTAS DE USUÁRIO (Cadastro, Login e Sair)
# ---------------------------------------------------------

# Rota para Sair (Logout)
@app.get("/sair")
def sair():
    resposta = RedirectResponse(url="/", status_code=303)
    resposta.delete_cookie("usuario_id")
    return resposta

# Rota para receber os dados do formulário de cadastro
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

# Rota para exibir a página de Login e Cadastro
@app.get("/login")
def pagina_login(request: Request):
    return templates.TemplateResponse(
        request=request, 
        name="login.html"
    )

# Rota POST para processar o Login
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

    # ---------------------------------------------------------
# PAINEL DO USUÁRIO (Gestão)
# ---------------------------------------------------------
@app.get("/painel")
def painel_usuario(request: Request):
    usuario_id = request.cookies.get("usuario_id")
    
    # Se não estiver logado, chuta para a tela de login
    if not usuario_id:
        return RedirectResponse(url="/login", status_code=303)
        
    conn = conectar_banco()
    
    # Pega os dados do usuário logado
    usuario = conn.execute("SELECT * FROM usuarios WHERE id = ?", (usuario_id,)).fetchone()
    
    # 1. Eventos que o usuário ORGANIZA
    # Transformamos em 'dict' (dicionário) para podermos adicionar a lista de inscritos dentro dele depois
    cursor_org = conn.execute("SELECT * FROM eventos WHERE criador_id = ?", (usuario_id,))
    eventos_organizados = [dict(row) for row in cursor_org.fetchall()]
    
    # Para cada evento que ele organiza, buscamos quem clicou em "Participar"
    for evento in eventos_organizados:
        cursor_inscritos = conn.execute('''
            SELECT usuarios.nome, usuarios.email 
            FROM inscricoes 
            JOIN usuarios ON inscricoes.usuario_id = usuarios.id 
            WHERE inscricoes.evento_id = ?
        ''', (evento["id"],))
        evento["inscritos"] = cursor_inscritos.fetchall()
        
    # 2. Eventos que o usuário PARTICIPA
    cursor_part = conn.execute('''
        SELECT eventos.* 
        FROM inscricoes 
        JOIN eventos ON inscricoes.evento_id = eventos.id 
        WHERE inscricoes.usuario_id = ?
    ''', (usuario_id,))
    eventos_participo = cursor_part.fetchall()
    
    conn.close()
    
    # Envia tudo para a nova tela html
    return templates.TemplateResponse(
        request=request, 
        name="painel.html",
        context={
            "usuario": usuario, 
            "organizados": eventos_organizados, 
            "participo": eventos_participo
        }
    )