# 🚀 Guia de Implantação e Uso

Este guia descreve como colocar o **Sistema de Enquetes Inteligente** em funcionamento utilizando Docker e como operar suas principais funcionalidades.

## 📋 Pré-requisitos

Para executar o sistema, você precisa ter instalado no servidor ou máquina local:

1. **Docker Engine**
2. **Docker Compose**

> **Nota:** Não é necessário instalar Python ou MySQL manualmente.

---

## 🐳 1. Inicializando o Sistema

O processo é automatizado via Docker Compose. Siga os passos abaixo:

### Passo 1: Configuração do Ambiente

Certifique-se de que o arquivo `docker-compose.yml` está na raiz do projeto.
*As senhas e chaves secretas já estão pré-configuradas no arquivo para o ambiente de desenvolvimento.*

### Passo 2: Subir os Contêineres

Abra o terminal na pasta do projeto e execute:

```bash
docker-compose up --build -d

```

* `--build`: Garante que a imagem da aplicação seja recriada com as últimas alterações.
* `-d`: Roda em segundo plano (modo "detached"), liberando o terminal.

### ⏳ O que esperar (Preload Automático)

Ao iniciar pela primeira vez, o sistema possui uma proteção de **"Wait-for-Database"**.
Se você verificar os logs (`docker-compose logs -f app`), poderá ver mensagens como:

> *"⚠️ Banco ainda não disponível. Tentando novamente em 2 segundos..."*

Isso é normal. A aplicação aguardará o MySQL terminar de configurar (o que pode levar de 30 a 60 segundos na primeira vez) e iniciará automaticamente assim que a conexão for estabelecida.

---

## 🌐 2. Acessando a Aplicação

Após a inicialização, os serviços estarão disponíveis nos seguintes endereços:

| Serviço | URL Local | Descrição |
| --- | --- | --- |
| **Aplicação Web** | [http://localhost:8000](https://www.google.com/search?q=http://localhost:8000) | Interface principal do sistema (Login/Votação). |
| **Documentação API** | [http://localhost:8000/docs](https://www.google.com/search?q=http://localhost:8000/docs) | Swagger UI para testar rotas do Backend. |

---

## 🔑 3. Primeiro Acesso (Super Admin)

O sistema cria automaticamente um Super Administrador na primeira execução.

1. Acesse **[http://localhost:8000/login](https://www.google.com/search?q=http://localhost:8000/login)**.
2. Utilize as credenciais padrão:
* **E-mail:** `admin@admin`
* **Senha:** `admin`


3. **Configuração Inicial:** Ao entrar, o sistema pode redirecioná-lo para uma tela de **Setup** para que você defina um novo e-mail seguro e altere a senha padrão.

---

## 🗳️ 4. Manual de Uso

### 👤 Para Criadores de Enquete

1. **Cadastro:** Se não for admin, clique em "Criar conta" na tela de login.
2. **Dashboard:** Após logar, você verá suas enquetes criadas.
3. **Criar Nova Enquete:**
* Clique no botão **"Criar Nova"**.
* **Título:** Defina a pergunta principal.
* **Texto Explicativo (Novo):** Ative esta opção para escrever um texto longo com regras ou contexto. Isso aparecerá num botão "Saiba Mais" para o votante.
* **Imagem de Capa:** Faça upload de uma imagem para ilustrar a votação (aparece no compartilhamento).
* **Prazo:** Defina data e hora para encerramento automático.
* **Opções:** Adicione quantas alternativas desejar.


4. **Compartilhar:** Copie o link público gerado (ex: `/polls/uuid-unico`) e envie para os participantes.

### 👥 Para Votantes

1. Acesse o link da enquete.
2. (Opcional) Clique em **"Saiba Mais"** para ler o texto explicativo (se houver).
3. Selecione a opção desejada (ou múltiplas, se permitido).
4. Clique em **"Confirmar Voto"**.
* *O sistema validará seu voto. Se você tentar votar novamente, será bloqueado pelo IP ou Cookie.*



### 🛡️ Para Administradores

1. Faça login com a conta de Admin.
2. Clique no botão **"Área Administrativa"** na barra superior ou no Dashboard.
3. **Aba Usuários:**
* Veja todos os usuários cadastrados.
* Use o botão **Bloquear** para suspender acesso imediato de usuários suspeitos.
* Use **Criar Admin** para promover outros usuários.


4. **Aba Enquetes:**
* Visualize todas as votações do sistema.
* **Alterar Prazo:** Estenda ou encerre prematuramente qualquer votação.
* **Arquivar:** Oculta a enquete do público sem apagar os dados.
* **Excluir:** Remove a enquete e todos os votos permanentemente.



---

## 🛠️ Comandos Úteis (Manutenção)

Caso precise gerenciar o ambiente, utilize os comandos abaixo na pasta do projeto:

* **Parar o sistema:**
```bash
docker-compose down

```


* **Ver logs em tempo real (para depuração):**
```bash
docker-compose logs -f

```


* **Acessar o terminal do container da aplicação:**
```bash
docker-compose exec app /bin/bash

```


* **Reiniciar apenas a aplicação (sem reiniciar o banco):**
```bash
docker-compose restart app

```