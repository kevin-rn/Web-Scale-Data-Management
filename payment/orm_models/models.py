from sqlalchemy import Column, Integer, Boolean, ForeignKey, Numeric
from sqlalchemy.dialects.postgresql import UUID, FLOAT
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

# ON DELETE CASCADE: https://stackoverflow.com/questions/5033547/sqlalchemy-cascade-delete
    # So, to delete an object and to let db handle the cascading deletions, use this syntax: session.query(Parent).filter(...).delete()
    # AND NOT this syntax: session.delete(parent_obj) so that individual DELETE operations are not emitted 
    # via ORM since no associated objects are present in memory 
# ON WHY cascade_backrefs is set to False in all the models: https://docs.sqlalchemy.org/en/14/changelog/migration_14.html#change-5150


class Payment(Base):
    """The Payment class corresponds to the "payments" database table.
    """
    __tablename__ = 'payments'

    payment_id = Column(Integer, autoincrement=True, primary_key=True)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey('users.user_id', ondelete="CASCADE"), 
        nullable=False
    )
    order_id = Column(
        UUID(as_uuid=True), 
        ForeignKey('orders.order_id', ondelete="CASCADE"), 
        nullable=False
    )
    amount = Column(FLOAT(precision=64, decimal_return_scale=None), nullable=False)
    
    def to_dict(self):
       return {c.name: getattr(self, c.name) for c in self.__table__.columns}

class User(Base):
    """The User class corresponds to the "users" database table.
    """
    __tablename__ = 'users'

    user_id = Column(UUID(as_uuid=True), primary_key=True)
    credit = Column(FLOAT(precision=64, decimal_return_scale=None), nullable=False, default=0)
    fk_order_ids = relationship(
        "Order",
        # cascade="all, delete", # if there are orders loaded with the associated user in a session, then DELETE query is emitted for each of the orders (deletion on ORM side)
        passive_deletes=True, # defers the deletion of children to the database
        backref='users', # any changes to the order objects is reflected back to the corresponding user object and vice versa (efficiency)
        cascade_backrefs=False
    )
    fk_payment_ids = relationship(
        "Payment",
        # cascade="all, delete", 
        passive_deletes=True,
        backref='users',
        cascade_backrefs=False
    )

    def to_dict(self):
       return {c.name: getattr(self, c.name) for c in self.__table__.columns}

class Order(Base):
    """The Order class corresponds to the "orders" database table.
    """
    __tablename__ = 'orders'

    order_id = Column(UUID(as_uuid=True), primary_key=True)
    user_id = Column(
        UUID(as_uuid=True), 
        ForeignKey('users.user_id', ondelete="CASCADE"), 
        nullable=False
    )
    fk_item_ids = relationship(
        "Cart",
        # cascade="all, delete",
        passive_deletes=True,
        backref='orders',
        cascade_backrefs=False
    )
    fk_payment_ids_order = relationship(
        "Payment",
        # cascade="all, delete",
        passive_deletes=True,
        backref='orders',
        cascade_backrefs=False
    )
    
    def to_dict(self):
       return {c.name: getattr(self, c.name) for c in self.__table__.columns}

class Cart(Base):
    """The Cart class corresponds to the "carts" database table.
    """
    __tablename__ = 'carts'

    id = Column(Integer, autoincrement=True, primary_key=True)
    item_id = Column(UUID(as_uuid=True), nullable=False)
    order_id = Column(
        UUID(as_uuid=True), 
        ForeignKey('orders.order_id', ondelete="CASCADE"), 
        nullable=False
    )

    def to_dict(self):
       return {c.name: getattr(self, c.name) for c in self.__table__.columns}

class Stock(Base):
    """The Stock class corresponds to the "stocks" database table.
    """
    __tablename__ = 'stocks'

    item_id = Column(UUID(as_uuid=True), primary_key=True)
    stock = Column(Integer, nullable=False, default=0)
    price = Column(FLOAT(precision=64, decimal_return_scale=None), nullable=False)

    def to_dict(self):
       return {c.name: getattr(self, c.name) for c in self.__table__.columns}
