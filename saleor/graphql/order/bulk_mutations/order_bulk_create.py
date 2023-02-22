from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

import graphene
from django.core.exceptions import ValidationError

from ....account.models import Address, User
from ....channel.models import Channel
from ....order.models import Order, OrderLine
from ....permission.enums import OrderPermissions
from ....product.models import ProductVariant
from ....shipping.models import ShippingMethod, ShippingMethodChannelListing
from ....tax.models import TaxClass
from ....warehouse.models import Warehouse
from ...account.i18n import I18nMixin
from ...account.types import AddressInput
from ...core import ResolveInfo
from ...core.enums import ErrorPolicy, ErrorPolicyEnum, LanguageCodeEnum
from ...core.mutations import BaseMutation
from ...core.scalars import PositiveDecimal, WeightScalar
from ...core.types import NonNullList
from ...core.types.common import OrderBulkCreateError
from ...core.utils import from_global_id_or_none
from ...meta.mutations import MetadataInput
from ..mutations.order_discount_common import OrderDiscountCommonInput
from ..types import Order as OrderType


@dataclass
class OrderBulkError:
    message: str
    code: Optional[str] = None


@dataclass
class OrderLineWithErrors:
    line: Optional[OrderLine]
    errors: List[OrderBulkError]


@dataclass
class OrderWithErrors:
    order: Optional[Order]
    lines: List[OrderLineWithErrors]
    errors: List[OrderBulkError]

    def get_all_errors(self) -> List[OrderBulkError]:
        return self.errors + [error for line in self.lines for error in line.errors]


@dataclass
class InstancesRelatedToOrder:
    user: User
    warehouse: Warehouse
    shipping_method: ShippingMethod
    shipping_tax_class: TaxClass
    billing_address: Address
    channel: Channel
    shipping_address: Optional[Address] = None


@dataclass
class OrderAmounts:
    shipping_price_gross: Decimal
    shipping_price_net: Decimal
    total_gross: Decimal
    total_net: Decimal
    undiscounted_total_gross: Decimal
    undiscounted_total_net: Decimal


class TaxedMoneyInput(graphene.InputObjectType):
    gross = PositiveDecimal(required=True, description="Gross value of an item.")
    net = PositiveDecimal(required=True, description="Net value of an item.")
    currency = graphene.String(required=True, description="Currency code.")


class OrderBulkCreateUserInput(graphene.InputObjectType):
    id = graphene.ID(description="Customer ID associated with the order.")
    email = graphene.String(description="Customer email associated with the order.")
    external_reference = graphene.String(
        description="Customer external ID associated with the order."
    )


class OrderBulkCreateDeliveryMethodInput(graphene.InputObjectType):
    warehouse_id = graphene.ID(description="The ID of the warehouse.")
    warehouse_name = graphene.String(description="The name of the warehouse.")
    shipping_method_id = graphene.ID(description="The ID of the shipping method.")
    shipping_method_name = graphene.String(
        description="The name of the shipping method."
    )
    shipping_price = graphene.Field(
        TaxedMoneyInput, description="The price of the shipping."
    )
    shipping_tax_rate = graphene.Float(
        required=True, description="Tax rate of the shipping."
    )
    shipping_tax_class_id = graphene.ID(description="The ID of the tax class.")
    shipping_tax_class_name = graphene.String(description="The name of the tax class.")
    shipping_tax_class_metadata = NonNullList(
        MetadataInput, description="Metadata of the tax class."
    )
    shipping_tax_class_private_metadata = NonNullList(
        MetadataInput, description="Private metadata of the tax class."
    )


class OrderBulkCreateNoteInput(graphene.InputObjectType):
    message = graphene.String(required=True, description="Note message.")
    date = graphene.DateTime(description="The date associated with the message.")
    user_id = graphene.ID(description="The user ID associated with the message.")
    app_id = graphene.ID(description="The app ID associated with the message.")


class OrderBulkCreateOrderLineInput(graphene.InputObjectType):
    variant_id = graphene.ID(description="The ID of the product variant.")
    variant_sku = graphene.String(description="The sku of the product variant.")
    variant_external_reference = graphene.String(
        description="The external ID of the product variant."
    )
    variant_name = graphene.String(description="The name of the product variant.")
    product_name = graphene.String(description="The name of the product.")
    translated_variant_name = graphene.String(
        description="Translation of the product variant name."
    )
    translated_product_name = graphene.String(
        description="Translation of the product name."
    )
    created_at = graphene.DateTime(
        required=True, description="The date, when the order line was created."
    )
    is_shipping_required = graphene.Boolean(
        required=True,
        description="Determines whether shipping of the order line items is required.",
    )
    is_gift_card = graphene.Boolean(required=True, description="Gift card flag.")
    quantity = graphene.Int(
        required=True, description="Number of items in the order line"
    )
    quantity_fulfilled = graphene.Int(
        required=True,
        description="Number of items in the order line, "
        "which have been already fulfilled.",
    )
    total_price = graphene.Field(
        TaxedMoneyInput, required=True, description="Price of the order line."
    )
    undiscounted_total_price = graphene.Field(
        TaxedMoneyInput,
        required=True,
        description="Price of the order line excluding applied discount.",
    )
    tax_rate = graphene.Float(required=True, description="Tax rate of the order line.")
    tax_class_id = graphene.ID(description="The ID of the tax class.")
    tax_class_name = graphene.String(description="The name of the tax class.")
    tax_class_metadata = NonNullList(
        MetadataInput, description="Metadata of the tax class."
    )
    tax_class_private_metadata = NonNullList(
        MetadataInput, description="Private metadata of the tax class."
    )


class OrderBulkCreateInput(graphene.InputObjectType):
    number = graphene.Int(description="Unique number of the order.")
    external_reference = graphene.String(description="External ID of the order.")
    channel = graphene.String(
        required=True, description="Slug of the channel associated with the order."
    )
    created_at = graphene.DateTime(
        required=True,
        description="The date, when the order was inserted to Saleor database.",
    )
    status = graphene.String(description="Status of the order.")
    user = graphene.Field(
        OrderBulkCreateUserInput,
        required=True,
        description="Customer accociated with the order.",
    )
    tracking_client_id = graphene.String(description="Tracking ID of the customer.")
    billing_address = graphene.Field(
        AddressInput, required=True, description="Billing address of the customer."
    )
    shipping_address = graphene.Field(
        AddressInput, description="Shipping address of the customer."
    )
    metadata = NonNullList(MetadataInput, description="Metadata of the order.")
    private_metadata = NonNullList(
        MetadataInput, description="Private metadata of the order."
    )
    customer_note = graphene.String(description="Note about customer.")
    notes = NonNullList(
        OrderBulkCreateNoteInput,
        description="Notes related to the order.",
    )
    language_code = graphene.Argument(
        LanguageCodeEnum, required=True, description="Order language code."
    )
    display_gross_prices = graphene.Boolean(
        description="Determines whether checkout prices should include taxes, "
        "when displayed in a storefront.",
    )
    weight = WeightScalar(description="Weight of the order.")
    redirect_url = graphene.String(
        description="URL of a view, where users should be redirected "
        "to see the order details.",
    )
    lines = NonNullList(
        OrderBulkCreateOrderLineInput, required=True, description="List of order lines."
    )
    delivery_method = graphene.Field(
        OrderBulkCreateDeliveryMethodInput,
        required=True,
        description="The delivery method selected for this order.",
    )
    promo_codes = NonNullList(graphene.String, description="List of promo codes.")
    discounts = NonNullList(OrderDiscountCommonInput, description="List of discounts.")
    # TODO notes
    # TODO invoices = [OrderBulkCreateInvoiceInput!]
    # TODO transactions: [TransactionCreateInput!]!
    # TODO fulfillments: [OrderBulkCreateFulfillmentInput!]
    # TODO weight = WeightScalar(description="Weight of the order.")
    # TODO discounts = NonNullList(OrderDiscountCommonInput, description="List of dis)


class OrderBulkCreateResult(graphene.ObjectType):
    order = graphene.Field(OrderType, description="Order data.")
    errors = NonNullList(
        OrderBulkCreateError,
        description="List of errors occurred on create attempt.",
    )


class OrderBulkCreate(BaseMutation, I18nMixin):
    count = graphene.Int(
        required=True,
        default_value=0,
        description="Returns how many objects were created.",
    )
    results = NonNullList(
        OrderBulkCreateResult,
        required=True,
        default_value=[],
        description="List of the created orders.",
    )

    class Arguments:
        orders = NonNullList(
            OrderBulkCreateInput,
            required=True,
            description="Input list of orders to create.",
        )
        error_policy = ErrorPolicyEnum(
            required=False,
            default_value=ErrorPolicyEnum.REJECT_EVERYTHING.value,
            description=(
                "Policies of error handling. DEFAULT: "
                + ErrorPolicyEnum.REJECT_EVERYTHING.name
            ),
        )

    class Meta:
        description = "Creates multiple orders."
        permissions = (OrderPermissions.MANAGE_ORDERS,)
        error_type_class = OrderBulkCreateError
        error_type_field = "bulk_order_errors"

    @classmethod
    def get_instance(cls, input: Dict[str, Any], model, key_map: Dict[str, str]):
        """Resolve instance based on input data, model and `key_map` argument provided.

        `input`: data from input
        `model`: database model associated with searched instance
        `key_map`: mapping between keys from input and keys from database

        Return model instance or rise error.
        """
        # TODO replace model with query set if additional filters needed
        if sum((input.get(key) is not None for key in key_map.keys())) > 1:
            args = ", ".join((k for k in key_map.keys()))
            raise ValidationError(
                f"Only one of [{args}] arguments can be provided "
                f"to resolve {model.__name__} instance."
            )

        if all((input.get(key) is None for key in key_map.keys())):
            args = ", ".join((k for k in key_map.keys()))
            raise ValidationError(
                f"One of [{args}] arguments must be provided "
                f"to resolve {model.__name__} instance."
            )

        for data_key, db_key in key_map.items():
            if input.get(data_key) and isinstance(input.get(data_key), str):
                if db_key == "id":
                    id = from_global_id_or_none(input.get(data_key), model.__name__)
                    if not id:
                        raise ValidationError(
                            f"Can't resolve global id: {input.get(data_key)}"
                        )
                    else:
                        input[data_key] = id

                return model.objects.filter(**{db_key: input.get(data_key)}).first()

        raise ValidationError(f"Can't return {model.__name__} instance.")

    @classmethod
    def get_instance_and_errors(
        cls,
        input: Dict[str, Any],
        model,
        key_map: Dict[str, str],
        errors: List[OrderBulkError],
    ):
        """Resolve instance based on input data, model and `key_map` argument provided.

        `input`: data from input
        `model`: database model associated with searched instance
        `key_map`: mapping between keys from input and keys from database
        `errors`: error list to be updated if an error occur

        Return model instance and error list.
        """
        instance = None
        try:
            instance = cls.get_instance(input, model, key_map)
        except ValidationError as err:
            errors.append(OrderBulkError(message=str(err.message)))
        return instance, errors

    @classmethod
    def create_single_order_line(
        cls, order_line_input: Dict[str, Any], order: Order
    ) -> OrderLineWithErrors:
        errors: List[OrderBulkError] = []

        variant, errors = cls.get_instance_and_errors(
            input=order_line_input,
            errors=errors,
            model=ProductVariant,
            key_map={
                "variant_id": "id",
                "variant_external_reference": "external_reference",
                "variant_sku": "sku",
            },
        )

        # TODO handle tax class metadata
        line_tax_class, errors = cls.get_instance_and_errors(
            input=order_line_input,
            errors=errors,
            model=TaxClass,
            key_map={"tax_class_id": "id", "tax_class_name": "name"},
        )

        if not all([variant, line_tax_class]):
            return OrderLineWithErrors(line=None, errors=errors)

        order_line_currency = order_line_input["total_price"]["currency"]
        order_line_gross_amount = order_line_input["total_price"]["gross"]
        order_line_net_amount = order_line_input["total_price"]["net"]
        order_line_quantity = order_line_input["quantity"]

        # TODO take into account quantity / fulfilled
        # TODO move to calculations / utils
        order_line_unit_price_net_amount = order_line_net_amount / order_line_quantity
        order_line_unit_price_gross_amount = (
            order_line_gross_amount / order_line_quantity
        )

        order_line = OrderLine(
            order=order,
            variant=variant,
            product_name="placeholder",
            variant_name=variant.name,
            product_sku=variant.sku,
            product_variant_id=variant.get_global_id(),
            is_shipping_required=variant.is_shipping_required(),
            is_gift_card=variant.is_gift_card(),
            quantity=order_line_quantity,
            quantity_fulfilled=order_line_input["quantity_fulfilled"],
            currency=order_line_currency,
            unit_price_net_amount=order_line_unit_price_net_amount,
            unit_price_gross_amount=order_line_unit_price_gross_amount,
            total_price_net_amount=order_line_net_amount,
            total_price_gross_amount=order_line_gross_amount,
            tax_class=line_tax_class,
            tax_class_name=line_tax_class.name,
            # TODO handle discounts
            # TODO handle taxes
        )

        return OrderLineWithErrors(line=order_line, errors=errors)

    @classmethod
    def get_instances_related_to_order(
        cls,
        order_input: Dict[str, Any],
        errors: List[OrderBulkError],
    ) -> Tuple[Optional[InstancesRelatedToOrder], List[OrderBulkError]]:
        """Get all instances of objects needed to create an order."""

        user, errors = cls.get_instance_and_errors(
            input=order_input["user"],
            errors=errors,
            model=User,
            key_map={
                "id": "id",
                "email": "email",
                "external_reference": "external_reference",
            },
        )
        # TODO check if zones etc needed
        warehouse, errors = cls.get_instance_and_errors(
            input=order_input["delivery_method"],
            errors=errors,
            model=Warehouse,
            key_map={"warehouse_id": "id", "warehouse_name": "name"},
        )
        # TODO check if zones etc needed
        shipping_method, errors = cls.get_instance_and_errors(
            input=order_input["delivery_method"],
            errors=errors,
            model=ShippingMethod,
            key_map={"shipping_method_id": "id", "shipping_method_name": "name"},
        )
        # TODO handle tax class metadata
        # TODO check if zones etc needed
        shipping_tax_class, errors = cls.get_instance_and_errors(
            input=order_input["delivery_method"],
            errors=errors,
            model=TaxClass,
            key_map={"shipping_tax_class_id": "id", "shipping_tax_class_name": "name"},
        )
        billing_address, shipping_address = None, None
        billing_address_input = order_input["billing_address"]
        try:
            billing_address = cls.validate_address(billing_address_input)
            billing_address.save()
            # TODO move saving
        except Exception as e:
            # TODO error
            print(e)
            pass

        if shipping_address_input := order_input["shipping_address"]:
            try:
                shipping_address = cls.validate_address(shipping_address_input)
                shipping_address.save()
                # TODO move saving
            except Exception as e:
                # TODO error
                print(e)
                pass

        channel = Channel.objects.get(slug=order_input["channel"])

        instances = None
        if all(
            [
                user,
                warehouse,
                shipping_method,
                shipping_tax_class,
                billing_address,
                channel,
            ]
        ):
            instances = InstancesRelatedToOrder(
                user=user,
                warehouse=warehouse,
                shipping_method=shipping_method,
                shipping_tax_class=shipping_tax_class,
                billing_address=billing_address,
                shipping_address=shipping_address,
                channel=channel,
            )

        return instances, errors

    @classmethod
    def make_calculations(
        cls, instances: InstancesRelatedToOrder, order_lines: List[OrderLine]
    ) -> OrderAmounts:
        """Calculate all order amount fields based on associated order lines."""

        shipping_price_gross_amount = (
            ShippingMethodChannelListing.objects.values_list("price_amount", flat=True)
            .filter(
                shipping_method_id=instances.shipping_method.id,
                channel_id=instances.channel.id,
            )
            .first()
        )
        if not shipping_price_gross_amount:
            shipping_price_gross_amount = Decimal("0.0")

        order_total_gross_amount = Decimal(
            sum((line.total_price_gross_amount for line in order_lines))
        )
        order_undiscounted_total_gross_amount = Decimal(order_total_gross_amount)
        order_total_net_amount = Decimal(
            sum((line.total_price_net_amount for line in order_lines))
        )
        order_undiscounted_total_net_amount = Decimal(order_total_net_amount)

        return OrderAmounts(
            shipping_price_gross=shipping_price_gross_amount,
            # TODO handle shipping_net_price
            shipping_price_net=shipping_price_gross_amount,
            total_gross=order_total_gross_amount,
            total_net=order_total_net_amount,
            undiscounted_total_gross=order_undiscounted_total_gross_amount,
            undiscounted_total_net=order_undiscounted_total_net_amount,
        )
        # TODO handle taxes

    @classmethod
    def create_single_order(
        cls,
        order_input,
        order: Order,
        order_lines_with_errors: List[OrderLineWithErrors],
    ) -> OrderWithErrors:
        errors: List[OrderBulkError] = []

        # get related instances
        instances, errors = cls.get_instances_related_to_order(
            order_input=order_input,
            errors=errors,
        )
        if not instances:
            return OrderWithErrors(
                order=None, lines=order_lines_with_errors, errors=errors
            )

        # calculate order amounts
        order_lines: List[OrderLine] = [
            line.line for line in order_lines_with_errors if line.line is not None
        ]
        order_amounts = cls.make_calculations(instances, order_lines)

        # build note
        # notes_input = order_input.get("notes")

        # order.number = order_input.get("number")
        order.external_reference = order_input.get("external_reference")
        order.channel = instances.channel
        order.created_at = order_input.get("created_at")
        order.status = order_input.get("status")
        order.user = instances.user
        order.billing_address = instances.billing_address
        order.shipping_address = instances.shipping_address
        order.language_code = order_input.get("language_code")
        order.user_email = instances.user.email
        order.shipping_method = instances.shipping_method
        order.shipping_method_name = instances.shipping_method.name
        order.collection_point = instances.warehouse
        order.collection_point_name = instances.warehouse.name
        order.shipping_price_gross_amount = order_amounts.shipping_price_gross
        # TODO handle gross/net
        order.shipping_price_net_amount = order_amounts.shipping_price_gross
        order.shipping_tax_class = instances.shipping_tax_class
        order.shipping_tax_class_name = instances.shipping_tax_class.name
        order.shipping_tax_rate = Decimal(
            order_input["delivery_method"]["shipping_tax_rate"]
        )
        order.total_gross_amount = order_amounts.total_gross
        order.undiscounted_total_gross_amount = order_amounts.undiscounted_total_gross
        order.total_net_amount = order_amounts.total_net
        order.undiscounted_total_net_amount = order_amounts.undiscounted_total_net
        order.customer_note = order_input.get("customer_note", "")
        order.redirect_url = order_input.get("redirect_url")
        # TODO charged
        # TODO authourized
        # TODO voucher
        # TODO gift cards
        # TODO weight

        return OrderWithErrors(
            order=order, lines=order_lines_with_errors, errors=errors
        )

    @classmethod
    def save_data(
        cls,
        orders_with_errors: List[OrderWithErrors],
        policy: ErrorPolicy,
    ):
        # TODO refcator with get_all_errors()
        errors: List[OrderBulkError] = [
            error for line in orders_with_errors for error in line.errors
        ]
        errors.extend(
            [
                error
                for order in orders_with_errors
                for line in order.lines
                for error in line.errors
            ]
        )

        if errors:
            for order in orders_with_errors:
                if policy == ErrorPolicy.REJECT_EVERYTHING:
                    order.order = None
                elif policy == ErrorPolicy.REJECT_FAILED_ROWS:
                    if order.get_all_errors():
                        order.order = None
            return orders_with_errors

        # TODO should we allow orders with failed lines?
        # elif policy == ErrorPolicy.IGNORE_FAILED and errors:
        #     # TODO handle IGNORE_FAILED
        #     pass

        # TODO save addresses
        OrderLine.objects.bulk_create(
            [
                line.line
                for order in orders_with_errors
                for line in order.lines
                if line.line
            ]
        )
        Order.objects.bulk_create(
            [order.order for order in orders_with_errors if order.order]
        )
        return orders_with_errors

    @classmethod
    def validate_input(cls, input):
        # TODO validate status
        # TODO validate number
        # TODO validate date created
        # TODO validate display gross prices
        pass

    @classmethod
    def create_note(cls, note_input):
        pass

    @classmethod
    def perform_mutation(cls, _root, _info: ResolveInfo, /, **data):
        # TODO post save actions

        orders_input = data["orders"]

        cls.validate_input(orders_input)

        order_lines_with_errors: List[OrderLineWithErrors] = []
        orders_with_errors: List[OrderWithErrors] = []
        for order_input in orders_input:
            order_lines_input = order_input["lines"]
            order = Order()
            for order_line_input in order_lines_input:
                order_lines_with_errors.append(
                    cls.create_single_order_line(order_line_input, order)
                )

            orders_with_errors.append(
                cls.create_single_order(
                    order_input,
                    order,
                    order_lines_with_errors,
                )
            )

        cls.save_data(orders_with_errors, data["error_policy"])

        results = [
            OrderBulkCreateResult(order=order.order, errors=order.get_all_errors())
            for order in orders_with_errors
        ]
        count = sum([order.order is not None for order in orders_with_errors])
        return OrderBulkCreate(count=count, results=results)
