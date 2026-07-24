# Apple Refurbished Inventory Monitoring

This context describes how matching refurbished Apple offers and their observable availability changes are understood.

## Language

**Listing**:
An Apple refurbished-store offer identified by a stable Apple product identifier or canonical product URL. Variants such as storage capacity or color are distinct Listings when Apple exposes them as distinct offers.
_Avoid_: Machine, physical device, product

**Listing Appearance**:
For one Subscription, the observable transition of a matching Listing from absent to present, or from not matching to matching. A Listing that remains continuously present and matching has only one Listing Appearance for that Subscription.
_Avoid_: New machine, restock, relisting

**Confirmed Disappearance**:
The state reached when a previously present Listing is absent from two consecutive trustworthy Inventory Observations. Failed or structurally untrustworthy checks do not provide absence evidence.
_Avoid_: Missing once, request failure, sold unit

**Inventory Observation**:
The set of Listings reliably observed as present during one successful check of the monitored Apple storefront. A failed request or untrustworthy response is not an Inventory Observation.
_Avoid_: Scrape, page refresh

**Evaluable Listing**:
A Listing for which every attribute required by a Subscription is known from the current catalog and product-detail observations. A Listing with any unavailable or ambiguous required attribute is unevaluable, not non-matching.
_Avoid_: Complete product, valid listing

**Notification Delivery**:
The delivery of one Notification Batch through one enabled Notification Channel. Each channel has independent delivery state, so one channel's success does not suppress retries for another channel.
_Avoid_: Alert status, notification result

**Expired Delivery**:
A Notification Delivery from which every included Listing Appearance became ineligible before delivery and therefore must no longer be attempted. A later Listing Appearance can belong to a new Notification Batch.
_Avoid_: Failed forever, late alert

**Notification Batch**:
The collection of new Listing Appearances discovered in one Inventory Observation and presented as one bulleted message. Listing-level matching and deduplication remain independent of batching.
_Avoid_: Digest, one alert

**Notification Channel**:
A configured destination type through which Notification Batches are delivered, such as Discord, email, or WhatsApp.
_Avoid_: App, notifier

**Operational Incident**:
A persistent or immediately severe condition that prevents trustworthy inventory observation, state management, or notification delivery. An incident is reported once when opened and once when recovered, rather than on every repeated failure.
_Avoid_: Exception, log error, inventory alert

**Subscription**:
A user's durably identified set of product attributes that determines which Listings are relevant. Attributes omitted from a Subscription do not affect matching, and matching history belongs to the Subscription's stable identity.
_Avoid_: Filter, search, configuration

**Storefront Region**:
The Apple refurbished storefront market being observed, which determines regional inventory and currency. It does not permanently determine the presentation language.
_Avoid_: Country, language, locale

**Storefront Locale**:
The language and regional presentation conventions used to read a Storefront Region and label user-facing notifications. A region may provide a default locale while still allowing an explicit locale choice.
_Avoid_: Region, translation
