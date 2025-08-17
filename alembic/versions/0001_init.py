from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0001_init"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
	# Получаем соединение
	conn = op.get_bind()

	# 1) Подключаем расширения
	op.execute("CREATE EXTENSION IF NOT EXISTS unaccent;")
	op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")

	# 2) Создаём таблицу опираясь на класс Document из app.models
	#    (требование — использовать класс из приложения)
	from app.models import Document
	Document.__table__.create(bind=conn, checkfirst=True)

	# 3) Добавляем tsvector-колонку для полнотекстового поиска
	op.add_column(
		"documents",
		sa.Column("search_vector", postgresql.TSVECTOR(), nullable=True),
	)

	# Заполняем существующие строки значением tsvector из content
	op.execute(
		"UPDATE documents SET search_vector = to_tsvector('simple', coalesce(content, ''));"
	)

	# Создаём функцию-триггер для автоматического обновления search_vector при INSERT/UPDATE
	op.execute(
		"""
		CREATE FUNCTION documents_search_vector_update() RETURNS trigger AS $$
		BEGIN
		  NEW.search_vector := to_tsvector('simple', coalesce(NEW.content, ''));
		  RETURN NEW;
		END
		$$ LANGUAGE plpgsql;
		"""
	)

	op.execute(
		"""
		CREATE TRIGGER documents_search_vector_trigger
		BEFORE INSERT OR UPDATE ON documents
		FOR EACH ROW EXECUTE FUNCTION documents_search_vector_update();
		"""
	)

	# 4) Создаём GIN-индекс по tsvector
	op.create_index(
		"ix_documents_search_vector",
		"documents",
		["search_vector"],
		unique=False,
		postgresql_using="gin",
	)

	# И создаём триграммный GIN-индекс по content
	# Используем прямый SQL, чтобы задать gin_trgm_ops
	op.execute(
		"CREATE INDEX IF NOT EXISTS ix_documents_content_trgm ON documents USING gin (content gin_trgm_ops);"
	)


def downgrade():
	# Удаляем индексы и триггер/функцию, колонку и саму таблицу
	# Drop GIN index on search_vector
	op.drop_index("ix_documents_search_vector", table_name="documents")

	# Drop trigram index on content
	op.execute("DROP INDEX IF EXISTS ix_documents_content_trgm;")

	# Drop trigger and function
	op.execute("DROP TRIGGER IF EXISTS documents_search_vector_trigger ON documents;")
	op.execute("DROP FUNCTION IF EXISTS documents_search_vector_update();")

	# Drop tsvector column
	op.drop_column("documents", "search_vector")

	# Drop table created from app.models.Document
	op.drop_table("documents")
