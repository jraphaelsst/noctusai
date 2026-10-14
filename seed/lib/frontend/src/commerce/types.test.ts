/**
 * Enum parity — the exact CONTRACT §1 value lists. The backend slice carries
 * the mirror test; if either side changes a value, one of the two fails.
 */
import { describe, it, expect } from 'vitest';
import {
  COUPON_KINDS,
  CONSENT_KINDS,
  FIELD_SOURCES,
  FULFILLMENT_TYPES,
  ORDER_STATUSES,
  ORDER_TRANSITIONS,
  CHARGE_ATTEMPT_STATUSES,
  PAYMENT_METHODS,
  REFUND_STATUSES,
  REMINDER_KINDS,
  PRIVACY_REQUEST_KINDS,
  PRODUCT_STATUSES,
  PRODUCT_TYPES,
  TAX_REGIMES,
  TAX_TREATMENTS,
} from './types';

describe('commerce enums (CONTRACT §1)', () => {
  it('matches the contract value lists exactly', () => {
    expect({
      ProductType: PRODUCT_TYPES,
      FulfillmentType: FULFILLMENT_TYPES,
      ProductStatus: PRODUCT_STATUSES,
      OrderStatus: ORDER_STATUSES,
      TaxRegime: TAX_REGIMES,
      TaxTreatment: TAX_TREATMENTS,
      CouponKind: COUPON_KINDS,
      ConsentKind: CONSENT_KINDS,
      PrivacyRequestKind: PRIVACY_REQUEST_KINDS,
      FieldSource: FIELD_SOURCES,
      PaymentMethod: PAYMENT_METHODS,
      RefundStatus: REFUND_STATUSES,
      ChargeAttemptStatus: CHARGE_ATTEMPT_STATUSES,
      ReminderKind: REMINDER_KINDS,
    }).toEqual({
      ProductType: ['digital', 'physical', 'service', 'print_on_demand'],
      FulfillmentType: ['digital_delivery', 'shipping', 'pickup', 'local_delivery', 'none'],
      ProductStatus: ['draft', 'in_review', 'published', 'unlisted', 'retired'],
      OrderStatus: [
        'created',
        'pending_payment',
        'paid',
        'expired',
        'failed',
        'cancelled',
        'refunded',
        'chargeback',
        'partially_refunded',
        'disputed',
      ],
      TaxRegime: ['mei', 'simples', 'lucro_presumido', 'lucro_real', 'outro'],
      TaxTreatment: ['service_nfse', 'rights_receipt', 'goods_nfe', 'none'],
      CouponKind: ['percent', 'fixed'],
      ConsentKind: ['terms', 'privacy', 'marketing', 'immediate_delivery_waiver'],
      PrivacyRequestKind: ['access', 'correction', 'deletion', 'portability', 'revoke_consent'],
      FieldSource: ['form', 'payment', 'staff'],
      PaymentMethod: ['pix', 'boleto', 'credit_card'],
      RefundStatus: ['requested', 'done', 'failed'],
      ChargeAttemptStatus: ['pending', 'paid', 'expired', 'cancelled', 'failed'],
      ReminderKind: ['before_expiry', 'after_expiry'],
    });
  });

  it('order transitions match the contract and only reference known statuses', () => {
    expect(ORDER_TRANSITIONS).toEqual({
      created: ['pending_payment', 'failed', 'cancelled'],
      pending_payment: ['paid', 'expired', 'failed', 'cancelled'],
      expired: ['paid', 'cancelled', 'pending_payment'],
      failed: ['pending_payment'],
      paid: ['refunded', 'chargeback', 'partially_refunded', 'disputed'],
      cancelled: [],
      refunded: [],
      chargeback: [],
      partially_refunded: ['partially_refunded', 'refunded', 'chargeback', 'disputed'],
      disputed: ['paid', 'partially_refunded', 'chargeback'],
    });
    for (const [from, tos] of Object.entries(ORDER_TRANSITIONS)) {
      expect(ORDER_STATUSES).toContain(from);
      for (const to of tos) expect(ORDER_STATUSES).toContain(to);
    }
  });
});
